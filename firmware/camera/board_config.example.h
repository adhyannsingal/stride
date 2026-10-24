#pragma once
// BLOCKED: fill from the exact W11 vendor schematic/example, then copy to
// ignored board_config.h. These values deliberately do not select another PCB.
#define STRIDE_W11_VERIFIED false
#define W11_PWDN -1
#define W11_RESET -1
#define W11_XCLK -1
#define W11_SDA -1
#define W11_SCL -1
#define W11_D0 -1
#define W11_D1 -1
#define W11_D2 -1
#define W11_D3 -1
#define W11_D4 -1
#define W11_D5 -1
#define W11_D6 -1
#define W11_D7 -1
#define W11_VSYNC -1
#define W11_HREF -1
#define W11_PCLK -1
static_assert(STRIDE_W11_VERIFIED, "W11 blocked: verify PCB revision, camera pin map, flash/PSRAM and vendor example first");
#define W11_XCLK_HZ 0
#define W11_USE_PSRAM false
#define W11_HMIRROR 0
#define W11_VFLIP 0
// Fill mirror/flip from actual upright, unmirrored image validation, not guesses.
