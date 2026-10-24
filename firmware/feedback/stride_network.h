#pragma once
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <atomic>
#include <time.h>
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

#include "phase4_protocol.h"
struct DeviceAck { char id[65],status[12]; };
struct SensorSnapshot { float cm; bool valid; stride::Band band; char active[65]; };
QueueHandle_t commandQueue, ackQueue;
SensorSnapshot sensorSnapshot={0,false,stride::Band::Unknown,{0}};
portMUX_TYPE snapshotLock=portMUX_INITIALIZER_UNLOCKED;
std::atomic<uint32_t> healthyAt{0};
String bootId;
int lastHttpCode=0;

String randomUuid() {
  char out[37];
  snprintf(out,sizeof(out),"%08lx-%04x-4%03x-a%03x-%04x%08lx",
           (unsigned long)esp_random(),(unsigned)(esp_random()&65535),
           (unsigned)(esp_random()&4095),(unsigned)(esp_random()&4095),
           (unsigned)(esp_random()&65535),(unsigned long)esp_random());
  return String(out);
}

bool jsonRequest(const String& path, JsonDocument& response, JsonDocument* payload=nullptr) {
  if(WiFi.status()!=WL_CONNECTED || time(nullptr)<1700000000) return false;
  WiFiClientSecure tls;
  tls.setCACert(STRIDE_ROOT_CA); tls.setHandshakeTimeout(2);
  HTTPClient http;
  http.setConnectTimeout(500); http.setTimeout(500);
  if(!http.begin(tls,String(STRIDE_BASE_URL)+path)) return false;
  http.addHeader("X-Device-Token",STRIDE_DEVICE_TOKEN);
  int code;
  if(payload) {
    String body; serializeJson(*payload,body);
    http.addHeader("Content-Type","application/json");
    code=http.POST(body);
  } else code=http.GET();
  lastHttpCode=code;
  bool ok=code>=200 && code<300;
  if(ok) {
    // Require bounded Content-Length; chunked/unknown-length responses fail closed.
    int len=http.getSize();
    if(len<0 || len>4096) ok=false;
    else {
      String body; body.reserve(len);
      uint32_t began=millis();
      while(body.length()<(size_t)len && millis()-began<500) {
        int c=tls.read(); if(c>=0) body+=(char)c; else delay(1);
      }
      ok=body.length()==(size_t)len && !deserializeJson(response,body);
    }
  }
  http.end();
  return ok;
}

bool reportAck(const char* id,const char* status) {
  JsonDocument ack,receipt;
  ack["device_id"]=STRIDE_DEVICE_ID; ack["command_id"]=id; ack["status"]=status;
  return jsonRequest(String("/devices/")+STRIDE_DEVICE_ID+"/ack",receipt,&ack);
}

void discardRemote() {
  RemoteCue cancel{}; cancel.pattern=stride::Pattern::None;
  xQueueOverwrite(commandQueue,&cancel);
}

void networkTask(void*) {
  if(!STRIDE_NETWORK_CONFIGURED || !String(STRIDE_BASE_URL).startsWith("https://") || !strlen(STRIDE_ROOT_CA)) vTaskDelete(nullptr);
  WiFi.mode(WIFI_STA); WiFi.begin(STRIDE_WIFI_SSID,STRIDE_WIFI_PASSWORD);
  configTime(0,0,"pool.ntp.org","time.nist.gov");
  uint64_t seq=0,uptime=0; uint32_t lastMillis=millis(),lastPoll=0,lastReconnect=0;
  String lastCommand;
  DeviceAck pendingAck{}; bool hasAck=false;
  for(;;) {
    uint32_t now=millis(); uptime+=(uint32_t)(now-lastMillis); lastMillis=now;
    if(WiFi.status()!=WL_CONNECTED) {
      healthyAt=0;
      if(now-lastReconnect>3000) { WiFi.reconnect(); lastReconnect=now; }
      vTaskDelay(pdMS_TO_TICKS(100)); continue;
    }
    SensorSnapshot snapshot;
    portENTER_CRITICAL(&snapshotLock); snapshot=sensorSnapshot; portEXIT_CRITICAL(&snapshotLock);
    JsonDocument telemetry,response;
    telemetry["device_id"]=STRIDE_DEVICE_ID; telemetry["boot_id"]=bootId;
    telemetry["sequence"]=++seq; telemetry["uptime_ms"]=uptime;
    telemetry["measurement_valid"]=snapshot.valid; telemetry["source"]="real";
    if(snapshot.valid) telemetry["distance_cm"]=snapshot.cm; else telemetry["distance_cm"]=nullptr;
    if(!jsonRequest("/telemetry",response,&telemetry)) {
      healthyAt=0; discardRemote(); vTaskDelay(pdMS_TO_TICKS(100)); continue;
    }
    healthyAt=millis();
    const char* nav=response["navigation_state"] | "";
    if(strcmp(nav,"guiding")) discardRemote();
    // Drain terminal ACKs in order. A lost ACK is retried, never re-executed.
    for(int n=0;n<4;n++) {
      if(!hasAck) hasAck=xQueueReceive(ackQueue,&pendingAck,0)==pdTRUE;
      if(!hasAck) break;
      if(reportAck(pendingAck.id,pendingAck.status)) hasAck=false;
      else {
        if(lastHttpCode>=400 && lastHttpCode<500 && lastHttpCode!=429) hasAck=false;
        else healthyAt=0;
        break;
      }
    }
    if(millis()-lastPoll>=100) {
      lastPoll=millis(); uint32_t began=millis();
      JsonDocument commands;
      bool ok=jsonRequest(String("/devices/")+STRIDE_DEVICE_ID+"/commands",commands);
      if(!ok) { healthyAt=0; discardRemote(); }
      else if(!commands["command"].isNull()) {
        RemoteCue cue{};
        if(decodePhase4Command(commands["command"].as<JsonObjectConst>(),
                              STRIDE_DEVICE_ID,STRIDE_SESSION_ID,bootId.c_str(),cue) && lastCommand!=cue.id) {
          lastCommand=cue.id; // A lost received ACK must never cause re-execution.
          if(cue.ttl<=millis()-began) { reportAck(cue.id,"expired"); continue; }
          // Backend rechecks revision, expiry and sensor state before execution.
          if(!reportAck(cue.id,"received")) { healthyAt=0; discardRemote(); continue; }
          cue.elapsed=millis()-began; cue.received=millis();
          // RTT includes the receipt ACK. Local loop checks TTL and sensor again.
          xQueueOverwrite(commandQueue,&cue);
        }
      }
    }
    vTaskDelay(pdMS_TO_TICKS(100));
  }
}
