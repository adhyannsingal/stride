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

struct RemoteCue {
  char id[65], generation[65];
  stride::Pattern pattern;
  uint32_t ttl, elapsed, received;
};
struct DeviceAck { char id[65],generation[65],status[12]; };
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
  http.addHeader("Authorization",String("Bearer ")+STRIDE_DEVICE_TOKEN);
  int code;
  if(payload) {
    String body; serializeJson(*payload,body);
    http.addHeader("Content-Type","application/json");
    code=http.POST(body);
  } else code=http.GET();
  lastHttpCode=code;
  bool ok=code>=200 && code<300;
  if(ok) {
    // Bound parsing memory; do not retain arbitrary response bodies.
    String body;
    int len=http.getSize();
    if(len<0 || len>4096) ok=false;
    else {
      body.reserve(len);
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

void networkTask(void*) {
  if(!STRIDE_NETWORK_CONFIGURED || !String(STRIDE_BASE_URL).startsWith("https://") || !strlen(STRIDE_ROOT_CA)) vTaskDelete(nullptr);
  WiFi.mode(WIFI_STA); WiFi.begin(STRIDE_WIFI_SSID,STRIDE_WIFI_PASSWORD);
  configTime(0,0,"pool.ntp.org","time.nist.gov");
  uint32_t seq=0,lastPoll=0,lastReconnect=0;
  String generation,lastCommand;
  DeviceAck pendingAck{}; bool hasAck=false;
  for(;;) {
    if(WiFi.status()!=WL_CONNECTED) {
      healthyAt=0;
      if(millis()-lastReconnect>3000) { WiFi.reconnect(); lastReconnect=millis(); }
      vTaskDelay(pdMS_TO_TICKS(200)); continue;
    }
    SensorSnapshot snapshot;
    portENTER_CRITICAL(&snapshotLock); snapshot=sensorSnapshot; portEXIT_CRITICAL(&snapshotLock);
    JsonDocument telemetry,response;
    telemetry["session_id"]=STRIDE_SESSION_ID; telemetry["device_id"]=STRIDE_DEVICE_ID;
    telemetry["boot_id"]=bootId; telemetry["sequence"]=++seq; telemetry["uptime_ms"]=millis();
    telemetry["valid"]=snapshot.valid;
    if(snapshot.valid) telemetry["distance_cm"]=snapshot.cm; else telemetry["distance_cm"]=nullptr;
    telemetry["local_alert"]=snapshot.band==stride::Band::Stop?"urgent":snapshot.band==stride::Band::Unknown?"sensor_fault":snapshot.band==stride::Band::Clear?"none":"warning";
    if(snapshot.active[0]) telemetry["active_command_id"]=snapshot.active; else telemetry["active_command_id"]=nullptr;
    if(!jsonRequest("/telemetry",response,&telemetry)) { healthyAt=0; vTaskDelay(pdMS_TO_TICKS(200)); continue; }
    const char* current=response["generation"] | "";
    if(!strlen(current)) current=response["command_generation"] | "";
    if(!strlen(current) || strlen(current)>64) { healthyAt=0; continue; }
    if(generation!=current) {
      generation=current; lastCommand=""; hasAck=false;
      DeviceAck retired{}; while(xQueueReceive(ackQueue,&retired,0)==pdTRUE) {}
      RemoteCue cancel{}; cancel.pattern=stride::Pattern::None;
      strlcpy(cancel.generation,current,sizeof(cancel.generation));
      xQueueOverwrite(commandQueue,&cancel);
    }
    healthyAt=millis();
    if(!hasAck) hasAck=xQueueReceive(ackQueue,&pendingAck,0)==pdTRUE;
    if(hasAck && generation!=pendingAck.generation) hasAck=false;
    if(hasAck) {
      JsonDocument ack,receipt;
      ack["session_id"]=STRIDE_SESSION_ID; ack["boot_id"]=bootId;
      ack["command_id"]=pendingAck.id; ack["generation"]=pendingAck.generation; ack["status"]=pendingAck.status;
      if(jsonRequest(String("/devices/")+STRIDE_DEVICE_ID+"/ack",receipt,&ack)) hasAck=false;
      else { healthyAt=0; if(lastHttpCode>=400 && lastHttpCode<500 && lastHttpCode!=429) hasAck=false; }
    }
    if(millis()-lastPoll>=500) {
      lastPoll=millis(); uint32_t began=millis();
      JsonDocument commands;
      bool ok=jsonRequest(String("/devices/")+STRIDE_DEVICE_ID+"/commands?session_id="+STRIDE_SESSION_ID+"&boot_id="+bootId,commands);
      if(!ok) healthyAt=0;
      else if(!commands["command"].isNull()) {
        JsonObject c=commands["command"];
        const char* id=c["command_id"] | "";
        const char* gen=c["generation"] | "";
        const char* sid=c["session_id"] | "";
        const char* bid=c["device_boot_id"] | "";
        const char* p=c["pattern"] | "";
        if(strlen(id)>0 && strlen(id)<=64 && generation==gen && String(sid)==STRIDE_SESSION_ID && String(bid)==bootId && lastCommand!=id) {
          RemoteCue cue{};
          strlcpy(cue.id,id,sizeof(cue.id)); strlcpy(cue.generation,gen,sizeof(cue.generation));
          cue.pattern=!strcmp(p,"left")?stride::Pattern::Left:!strcmp(p,"right")?stride::Pattern::Right:!strcmp(p,"straight")?stride::Pattern::Straight:!strcmp(p,"stop")?stride::Pattern::Stop:stride::Pattern::None;
          cue.ttl=c["remaining_ttl_ms"] | 0u; cue.elapsed=millis()-began; cue.received=millis();
          xQueueOverwrite(commandQueue,&cue); lastCommand=id;
        }
      }
    }
    vTaskDelay(pdMS_TO_TICKS(200));
  }
}
