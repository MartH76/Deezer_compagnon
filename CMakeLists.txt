# Generated Cmake Pico project file (fusionne avec le firmware Deezer)

cmake_minimum_required(VERSION 3.13)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# == DO NOT EDIT THE FOLLOWING LINES for the Raspberry Pi Pico VS Code Extension to work ==
if(WIN32)
    set(USERHOME $ENV{USERPROFILE})
else()
    set(USERHOME $ENV{HOME})
endif()
set(sdkVersion 2.3.0)
set(toolchainVersion 15_2_Rel1)
set(picotoolVersion 2.3.0)
set(picoVscode ${USERHOME}/.pico-sdk/cmake/pico-vscode.cmake)
if (EXISTS ${picoVscode})
    include(${picoVscode})
endif()
# ====================================================================================
set(PICO_BOARD pico2_w CACHE STRING "Board type")

# Pull in Raspberry Pi Pico SDK (must be before project)
include(pico_sdk_import.cmake)

project(Deezer_compagnon C CXX ASM)

# Initialise the Raspberry Pi Pico SDK
pico_sdk_init()

# ---- LVGL v9 recupere automatiquement au premier build (git requis) ----
include(FetchContent)
set(LV_CONF_PATH ${CMAKE_CURRENT_LIST_DIR}/lv_conf.h CACHE FILEPATH "chemin lv_conf.h" FORCE)
FetchContent_Declare(lvgl
    GIT_REPOSITORY https://github.com/lvgl/lvgl.git
    GIT_TAG v9.2.2
)
FetchContent_MakeAvailable(lvgl)

# LVGL globe src/*.S et compile les fichiers assembleur Helium/NEON sans condition.
# Or ceux-ci incluent des en-tetes C avant tout garde -> l'assembleur ARM plante
# ("bad instruction: typedef ..."). On les retire : rendu software C pur (ASM=NONE).
get_target_property(_lvgl_srcs lvgl SOURCES)
list(FILTER _lvgl_srcs EXCLUDE REGEX "\\.S$")
set_target_properties(lvgl PROPERTIES SOURCES "${_lvgl_srcs}")

target_include_directories(lvgl PUBLIC ${CMAKE_CURRENT_LIST_DIR})

# ---- Executable ----
add_executable(Deezer_compagnon
    src/main.c
    src/gc9a01.c
    src/lvgl_port.c
    src/usb_proto.c
    src/ui.c
    src/encoder.c
    src/lv_font_dz_title_22.c
    src/lv_font_dz_artist_16.c
)

pico_set_program_name(Deezer_compagnon "Deezer_compagnon")
pico_set_program_version(Deezer_compagnon "0.1")

# USB CDC pour la liaison serie, UART desactive
pico_enable_stdio_uart(Deezer_compagnon 0)
pico_enable_stdio_usb(Deezer_compagnon 1)

target_include_directories(Deezer_compagnon PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}
    ${CMAKE_CURRENT_LIST_DIR}/src
)
target_compile_definitions(Deezer_compagnon PRIVATE LV_CONF_INCLUDE_SIMPLE)

target_link_libraries(Deezer_compagnon
    pico_stdlib
    hardware_spi
    hardware_dma
    lvgl
)

pico_add_extra_outputs(Deezer_compagnon)
