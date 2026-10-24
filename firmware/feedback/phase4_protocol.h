#pragma once
#include <ArduinoJson.h>
#include <cstring>
#include "controller.h"

struct RemoteCue {
  char id[65];
  stride::Pattern pattern;
  uint32_t ttl, elapsed, received;
};

// Shared by the ESP32 transport and host contract check against actual API JSON.
inline bool decodePhase4Command(JsonObjectConst c, const char* device,
                               const char* session, const char* boot, RemoteCue& cue) {
  const char* id=c["command_id"] | "";
  const char* sid=c["session_id"] | "";
  const char* bid=c["boot_id"] | "";
  const char* did=c["device_id"] | "";
  const char* kind=c["kind"] | "";
  const char* state=c["status"] | "";
  const char* navigation=c["navigation_id"] | "";
  if(!id[0] || strlen(id)>64 || strcmp(did,device) || strcmp(sid,session) ||
     strcmp(bid,boot) || strcmp(state,"delivered") || !navigation[0] ||
     !c["state_revision"].is<uint64_t>() || !c["remaining_ttl_ms"].is<uint32_t>()) return false;
  uint32_t ttl=c["remaining_ttl_ms"].as<uint32_t>();
  if(!ttl || ttl>1500) return false;
  stride::Pattern pattern;
  if(!strcmp(kind,"left")) pattern=stride::Pattern::Left;
  else if(!strcmp(kind,"right")) pattern=stride::Pattern::Right;
  else if(!strcmp(kind,"straight")) pattern=stride::Pattern::Straight;
  else if(!strcmp(kind,"stop")) pattern=stride::Pattern::Stop;
  else if(!strcmp(kind,"cancel")) pattern=stride::Pattern::None;
  else return false;
  std::memcpy(cue.id,id,strlen(id)+1);
  cue.pattern=pattern; cue.ttl=ttl; cue.elapsed=cue.received=0;
  return true;
}
