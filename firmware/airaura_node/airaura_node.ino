/*
  AirAura Node firmware v0.2.0
  ESP32 + PMS5003 (UART2) + DHT11/DHT22 + MQ-2/MQ-135 module (digital DO, optional analog AO)

  Every 60 s: median of all samples collected in that minute -> JSON POST to
  SERVER_URL/api/ingest with header X-Node-Key.
  Offline: readings are buffered in LittleFS (max 500) and resent later.
  Dedup key on the server: (node_id, boot_id, seq) — so reflashing/rebooting
  never causes real data to be dropped as "duplicate".

  Libraries: "DHT sensor library" + "Adafruit Unified Sensor" (Adafruit).
  Board: ESP32 Dev Module (arduino-esp32 core 2.x or 3.x).
*/
#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <LittleFS.h>
#include <DHT.h>
#include <time.h>
#include <algorithm>

#if __has_include("config.h")
#include "config.h"
#else
#error "Copy config.example.h to config.h and fill in your WiFi + server details"
#endif

#define FW_VERSION "0.2.0"
#define MAX_SAMPLES 150
#define BUFFER_FILE "/buffer.jsonl"
#define BUFFER_MAX_LINES 500

DHT dht(DHT_PIN, DHT_TYPE);
WebServer server(80);

// ---------- sample buffers for the current minute ----------
uint16_t pm1S[MAX_SAMPLES], pm25S[MAX_SAMPLES], pm10S[MAX_SAMPLES];
int pmN = 0;
float tS[MAX_SAMPLES], hS[MAX_SAMPLES];
int dhtN = 0;
float gasMvS[MAX_SAMPLES];
int gasMvN = 0;
int gasChecks = 0, gasAlarms = 0;

// ---------- latest values (for local page / serial) ----------
uint16_t lastPm1 = 0, lastPm25 = 0, lastPm10 = 0;
float lastT = NAN, lastH = NAN;
bool lastGasAlarm = false;
unsigned long lastPmsFrameMs = 0;
String lastUploadStatus = "not sent yet";

uint32_t bootId = 0;
uint32_t seqNo = 0;
unsigned long lastSendMs = 0, lastDhtMs = 0, lastGasMs = 0, lastWifiTryMs = 0;
bool timeSynced = false;

// ---------- PMS5003 frame parser (active mode, 32-byte frames) ----------
uint8_t pmsBuf[32];
int pmsIdx = 0;

void readPMS() {
  while (Serial2.available()) {
    uint8_t b = Serial2.read();
    if (pmsIdx == 0 && b != 0x42) continue;
    if (pmsIdx == 1 && b != 0x4D) { pmsIdx = 0; continue; }
    pmsBuf[pmsIdx++] = b;
    if (pmsIdx < 32) continue;
    pmsIdx = 0;
    uint16_t len = ((uint16_t)pmsBuf[2] << 8) | pmsBuf[3];
    uint16_t sum = 0;
    for (int i = 0; i < 30; i++) sum += pmsBuf[i];
    uint16_t rx = ((uint16_t)pmsBuf[30] << 8) | pmsBuf[31];
    if (len != 28 || sum != rx) continue;
    // "atmospheric environment" values (bytes 10-15)
    lastPm1  = ((uint16_t)pmsBuf[10] << 8) | pmsBuf[11];
    lastPm25 = ((uint16_t)pmsBuf[12] << 8) | pmsBuf[13];
    lastPm10 = ((uint16_t)pmsBuf[14] << 8) | pmsBuf[15];
    lastPmsFrameMs = millis();
    if (pmN < MAX_SAMPLES) {
      pm1S[pmN] = lastPm1; pm25S[pmN] = lastPm25; pm10S[pmN] = lastPm10; pmN++;
    }
  }
}

bool pmsOnline() { return lastPmsFrameMs && millis() - lastPmsFrameMs < 10000; }

// ---------- DHT every 2.5 s, gas every 1 s ----------
void sampleSlowSensors() {
  unsigned long now = millis();
  if (now - lastDhtMs >= 2500) {
    lastDhtMs = now;
    float t = dht.readTemperature();
    float h = dht.readHumidity();
    if (!isnan(t) && !isnan(h) && h >= 0 && h <= 100 && t > -20 && t < 60) {
      lastT = t; lastH = h;
      if (dhtN < MAX_SAMPLES) { tS[dhtN] = t; hS[dhtN] = h; dhtN++; }
    }
  }
  if (now - lastGasMs >= 1000) {
    lastGasMs = now;
    int s = digitalRead(GAS_DO_PIN);
    lastGasAlarm = GAS_ACTIVE_LOW ? (s == LOW) : (s == HIGH);
    gasChecks++;
    if (lastGasAlarm) gasAlarms++;
    if (GAS_AO_PIN >= 0 && gasMvN < MAX_SAMPLES) {
      gasMvS[gasMvN++] = analogReadMilliVolts(GAS_AO_PIN) * GAS_AO_DIVIDER;
    }
  }
}

// ---------- medians ----------
float medianU16(uint16_t* a, int n) {
  uint16_t tmp[MAX_SAMPLES];
  memcpy(tmp, a, n * sizeof(uint16_t));
  std::sort(tmp, tmp + n);
  return (n % 2) ? tmp[n / 2] : (tmp[n / 2 - 1] + tmp[n / 2]) / 2.0f;
}
float medianF(float* a, int n) {
  float tmp[MAX_SAMPLES];
  memcpy(tmp, a, n * sizeof(float));
  std::sort(tmp, tmp + n);
  return (n % 2) ? tmp[n / 2] : (tmp[n / 2 - 1] + tmp[n / 2]) / 2.0f;
}

// ---------- WiFi + time ----------
void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  if (millis() - lastWifiTryMs < 15000 && lastWifiTryMs != 0) return;
  lastWifiTryMs = millis();
  Serial.printf("[wifi] connecting to %s ...\n", WIFI_SSID);
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASS);
}

void checkTime() {
  if (timeSynced) return;
  if (time(nullptr) > 1700000000) {
    timeSynced = true;
    Serial.println("[time] NTP synced");
  }
}

String isoNow() {
  time_t now = time(nullptr);
  struct tm t;
  gmtime_r(&now, &t);
  char buf[25];
  strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &t);
  return String(buf);
}

// ---------- HTTP ----------
int postJson(const String& body) {
  if (WiFi.status() != WL_CONNECTED) return -1;
  String url = String(SERVER_URL) + "/api/ingest";
  HTTPClient http;
  WiFiClientSecure secure;
  WiFiClient plain;
  bool ok;
  if (url.startsWith("https")) {
    secure.setInsecure();  // TODO: pin the server's root CA for production
    ok = http.begin(secure, url);
  } else {
    ok = http.begin(plain, url);
  }
  if (!ok) return -1;
  http.setTimeout(10000);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Node-Key", NODE_KEY);
  int code = http.POST(body);
  http.end();
  return code;
}

// ---------- offline buffer (LittleFS, newline-delimited JSON) ----------
void bufferAppend(const String& line) {
  File f = LittleFS.open(BUFFER_FILE, FILE_APPEND);
  if (!f) return;
  f.println(line);
  f.close();
  // trim to the newest BUFFER_MAX_LINES
  File r = LittleFS.open(BUFFER_FILE, FILE_READ);
  int lines = 0;
  while (r.available()) { r.readStringUntil('\n'); lines++; }
  r.close();
  if (lines <= BUFFER_MAX_LINES) return;
  int skip = lines - BUFFER_MAX_LINES;
  r = LittleFS.open(BUFFER_FILE, FILE_READ);
  File w = LittleFS.open("/buffer.tmp", FILE_WRITE);
  int i = 0;
  while (r.available()) {
    String l = r.readStringUntil('\n');
    if (i++ >= skip && l.length() > 2) w.println(l);
  }
  r.close(); w.close();
  LittleFS.remove(BUFFER_FILE);
  LittleFS.rename("/buffer.tmp", BUFFER_FILE);
}

void flushBuffer() {
  if (WiFi.status() != WL_CONNECTED || !LittleFS.exists(BUFFER_FILE)) return;
  File r = LittleFS.open(BUFFER_FILE, FILE_READ);
  File w = LittleFS.open("/buffer.tmp", FILE_WRITE);
  int sent = 0, kept = 0;
  bool stop = false;
  while (r.available()) {
    String l = r.readStringUntil('\n');
    l.trim();
    if (l.length() < 3) continue;
    if (!stop && sent < 50) {           // max 50 per cycle so the loop stays responsive
      int code = postJson(l);
      if (code == 200 || code == 422) { sent++; continue; }  // 422 = bad row, drop it
      stop = true;
    }
    w.println(l); kept++;
  }
  r.close(); w.close();
  LittleFS.remove(BUFFER_FILE);
  if (kept > 0) LittleFS.rename("/buffer.tmp", BUFFER_FILE);
  else LittleFS.remove("/buffer.tmp");
  if (sent) Serial.printf("[buffer] resent %d, still queued %d\n", sent, kept);
}

// ---------- build + send one reading ----------
void sendReading() {
  bool warm = millis() < WARMUP_MS;
  String j = "{";
  j += "\"node_id\":\"" NODE_ID "\",";
  j += "\"boot_id\":" + String(bootId) + ",";
  j += "\"seq\":" + String(seqNo++) + ",";
  if (timeSynced) j += "\"ts\":\"" + isoNow() + "\",";
  if (pmN > 0) {
    j += "\"pm1\":" + String(medianU16(pm1S, pmN), 1) + ",";
    j += "\"pm25\":" + String(medianU16(pm25S, pmN), 1) + ",";
    j += "\"pm10\":" + String(medianU16(pm10S, pmN), 1) + ",";
  } else {
    j += "\"pm1\":null,\"pm25\":null,\"pm10\":null,";
  }
  j += "\"pm_samples\":" + String(pmN) + ",";
  if (dhtN > 0) {
    j += "\"temp_c\":" + String(medianF(tS, dhtN), 1) + ",";
    j += "\"rh_pct\":" + String(medianF(hS, dhtN), 1) + ",";
  } else {
    j += "\"temp_c\":null,\"rh_pct\":null,";
  }
  j += "\"gas_sensor\":\"" GAS_SENSOR "\",";
  float frac = gasChecks ? (float)gasAlarms / gasChecks : 0.0f;
  j += "\"gas_alarm\":" + String(frac >= 0.5f ? "true" : "false") + ",";
  j += "\"gas_alarm_frac\":" + String(frac, 2) + ",";
  if (gasMvN > 0) j += "\"gas_mv\":" + String(medianF(gasMvS, gasMvN), 0) + ",";
  else j += "\"gas_mv\":null,";
  j += "\"warmup\":" + String(warm ? "true" : "false") + ",";
  j += "\"rssi\":" + String(WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0) + ",";
  j += "\"fw\":\"" FW_VERSION "\"}";

  // reset the minute's samples
  pmN = dhtN = gasMvN = gasChecks = gasAlarms = 0;

  Serial.println("[reading] " + j);
  int code = postJson(j);
  if (code == 200) {
    lastUploadStatus = "OK " + isoNow();
    flushBuffer();
  } else if (code == 401) {
    lastUploadStatus = "401 wrong NODE_KEY / NODE_ID";
    Serial.println("[http] 401 — check NODE_KEY matches backend NODE_API_KEY");
  } else if (code == 422) {
    lastUploadStatus = "422 payload rejected";
    Serial.println("[http] 422 — backend rejected payload (see server log)");
  } else {
    lastUploadStatus = "failed (" + String(code) + "), buffered";
    Serial.printf("[http] failed %d — buffering\n", code);
    if (timeSynced) bufferAppend(j);  // only buffer readings that carry their own timestamp
  }
}

// ---------- local status page ----------
void handleLocalApi() {
  String j = "{";
  j += "\"pm1\":" + String(lastPm1) + ",\"pm25\":" + String(lastPm25) + ",\"pm10\":" + String(lastPm10);
  j += ",\"temp\":" + (isnan(lastT) ? String("null") : String(lastT, 1));
  j += ",\"hum\":" + (isnan(lastH) ? String("null") : String(lastH, 1));
  j += ",\"gas_alarm\":" + String(lastGasAlarm ? "true" : "false");
  j += ",\"pms\":" + String(pmsOnline() ? "true" : "false");
  j += ",\"wifi_rssi\":" + String(WiFi.RSSI());
  j += ",\"time_synced\":" + String(timeSynced ? "true" : "false");
  j += ",\"upload\":\"" + lastUploadStatus + "\"";
  j += ",\"boot_id\":" + String(bootId) + ",\"seq\":" + String(seqNo) + "}";
  server.send(200, "application/json", j);
}

const char page[] PROGMEM = R"HTML(<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AirAura Node</title><style>body{font-family:Arial;background:#0b1120;color:#e2e8f0;padding:16px}
.g{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}.c{background:#111827;border:1px solid #1e293b;padding:14px;border-radius:10px}
.l{font-size:12px;color:#94a3b8}.v{font-size:26px;font-weight:bold}</style></head><body>
<h3>AirAura Node — local status</h3><div class="g" id="g"></div><p class="l" id="u"></p>
<script>async function f(){try{const d=await (await fetch('/api')).json();
const it=[['PM1',d.pm1,'µg/m³'],['PM2.5',d.pm25,'µg/m³'],['PM10',d.pm10,'µg/m³'],['Temp',d.temp??'--','°C'],['Humidity',d.hum??'--','%'],['Gas',d.gas_alarm?'ALARM':'normal','']];
document.getElementById('g').innerHTML=it.map(i=>`<div class=c><div class=l>${i[0]}</div><div class=v>${i[1]}</div><div class=l>${i[2]}</div></div>`).join('');
document.getElementById('u').textContent=`PMS ${d.pms?'online':'OFFLINE'} · WiFi ${d.wifi_rssi} dBm · time ${d.time_synced?'synced':'not synced'} · last upload: ${d.upload} · seq ${d.seq}`;}catch(e){}}
setInterval(f,2000);f();</script></body></html>)HTML";

// ---------- setup / loop ----------
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\nAirAura node " FW_VERSION " starting");

  pinMode(GAS_DO_PIN, INPUT);
  if (GAS_AO_PIN >= 0) analogSetPinAttenuation(GAS_AO_PIN, ADC_11db);
  dht.begin();
  Serial2.begin(9600, SERIAL_8N1, PMS_RX, PMS_TX);

  if (!LittleFS.begin(true)) Serial.println("[fs] LittleFS mount failed — offline buffer disabled");

  bootId = esp_random();
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  ensureWifi();
  configTime(0, 0, "pool.ntp.org", "time.google.com");

  if (ENABLE_LOCAL_PAGE) {
    server.on("/", []() { server.send_P(200, "text/html", page); });
    server.on("/api", handleLocalApi);
    server.begin();
  }
  lastSendMs = millis();
}

void loop() {
  static bool printedIp = false;
  readPMS();
  sampleSlowSensors();
  ensureWifi();
  checkTime();
  if (WiFi.status() == WL_CONNECTED && !printedIp) {
    printedIp = true;
    Serial.print("[wifi] connected, node page: http://");
    Serial.println(WiFi.localIP());
  }
  if (WiFi.status() != WL_CONNECTED) printedIp = false;
  if (ENABLE_LOCAL_PAGE) server.handleClient();

  if (millis() - lastSendMs >= SEND_INTERVAL_MS) {
    lastSendMs = millis();
    sendReading();
  }
  delay(2);
}
