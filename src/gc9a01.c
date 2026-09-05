#include "gc9a01.h"
#include "config.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"
#include "hardware/dma.h"
#include "pico/time.h"

/* CS actif bas */
static inline void cs_sel(bool on)  { gpio_put(PIN_CS, on ? 0 : 1); }
static inline void dc_data(bool on) { gpio_put(PIN_DC, on ? 1 : 0); }

/* --- DMA --- */
static int dma_chan = -1;
static dma_channel_config dma_cfg;
static void (*done_cb)(void) = NULL;

static void dma_handler(void) {
    if (dma_hw->ints0 & (1u << dma_chan)) {
        dma_hw->ints0 = (1u << dma_chan);                 /* acquitte l'IRQ */
        /* attendre la fin reelle du shift SPI avant de relacher CS */
        while (spi_get_hw(LCD_SPI)->sr & SPI_SSPSR_BSY_BITS) tight_loop_contents();
        cs_sel(false);
        if (done_cb) done_cb();
    }
}

void gc9a01_set_done_cb(void (*cb)(void)) { done_cb = cb; }

/* --- ecriture bloquante (init / fenetre) --- */
static void wr_cmd(uint8_t c) {
    dc_data(false); cs_sel(true);
    spi_write_blocking(LCD_SPI, &c, 1);
    cs_sel(false);
}
static void wr_data(const uint8_t *d, size_t n) {
    dc_data(true); cs_sel(true);
    spi_write_blocking(LCD_SPI, d, n);
    cs_sel(false);
}
static void wr_d8(uint8_t v) { wr_data(&v, 1); }

void gc9a01_backlight(bool on) {
#if HAVE_BACKLIGHT
    gpio_put(PIN_BL, on ? 1 : 0);
#else
    (void)on;
#endif
}

void gc9a01_set_window(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1) {
    uint8_t col[4] = { (uint8_t)(x0 >> 8), (uint8_t)x0, (uint8_t)(x1 >> 8), (uint8_t)x1 };
    uint8_t row[4] = { (uint8_t)(y0 >> 8), (uint8_t)y0, (uint8_t)(y1 >> 8), (uint8_t)y1 };
    wr_cmd(0x2A); wr_data(col, 4);   /* CASET */
    wr_cmd(0x2B); wr_data(row, 4);   /* RASET */
    wr_cmd(0x2C);                    /* RAMWR : les pixels suivent */
}

void gc9a01_blit_dma(const uint8_t *data, size_t len) {
    dc_data(true);
    cs_sel(true);                    /* CS bas, relache dans l'IRQ de fin */
    dma_channel_configure(dma_chan, &dma_cfg,
                          &spi_get_hw(LCD_SPI)->dr,  /* destination : registre SPI */
                          data,                      /* source : buffer pixels */
                          len,                       /* nb d'octets */
                          true);                     /* demarre */
}

void gc9a01_init(void) {
    /* --- SPI + GPIO --- */
    spi_init(LCD_SPI, LCD_SPI_HZ);
    gpio_set_function(PIN_SCK, GPIO_FUNC_SPI);
    gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI);

    gpio_init(PIN_CS);  gpio_set_dir(PIN_CS, GPIO_OUT);  gpio_put(PIN_CS, 1);
    gpio_init(PIN_DC);  gpio_set_dir(PIN_DC, GPIO_OUT);
    gpio_init(PIN_RST); gpio_set_dir(PIN_RST, GPIO_OUT);
#if HAVE_BACKLIGHT
    gpio_init(PIN_BL);  gpio_set_dir(PIN_BL, GPIO_OUT);  gpio_put(PIN_BL, 0);
#endif

    /* --- Reset materiel --- */
    gpio_put(PIN_RST, 1); sleep_ms(10);
    gpio_put(PIN_RST, 0); sleep_ms(10);
    gpio_put(PIN_RST, 1); sleep_ms(120);

    /* --- DMA vers le SPI --- */
    dma_chan = dma_claim_unused_channel(true);
    dma_cfg = dma_channel_get_default_config(dma_chan);
    channel_config_set_transfer_data_size(&dma_cfg, DMA_SIZE_8);
    channel_config_set_dreq(&dma_cfg, spi_get_dreq(LCD_SPI, true));
    channel_config_set_read_increment(&dma_cfg, true);
    channel_config_set_write_increment(&dma_cfg, false);
    dma_channel_set_irq0_enabled(dma_chan, true);
    irq_set_exclusive_handler(DMA_IRQ_0, dma_handler);
    irq_set_enabled(DMA_IRQ_0, true);

    /* --- Sequence d'init GC9A01 (registres constructeur) --- */
    wr_cmd(0xEF);
    wr_cmd(0xEB); wr_d8(0x14);
    wr_cmd(0xFE);
    wr_cmd(0xEF);
    wr_cmd(0xEB); wr_d8(0x14);
    wr_cmd(0x84); wr_d8(0x40);
    wr_cmd(0x85); wr_d8(0xFF);
    wr_cmd(0x86); wr_d8(0xFF);
    wr_cmd(0x87); wr_d8(0xFF);
    wr_cmd(0x88); wr_d8(0x0A);
    wr_cmd(0x89); wr_d8(0x21);
    wr_cmd(0x8A); wr_d8(0x00);
    wr_cmd(0x8B); wr_d8(0x80);
    wr_cmd(0x8C); wr_d8(0x01);
    wr_cmd(0x8D); wr_d8(0x01);
    wr_cmd(0x8E); wr_d8(0xFF);
    wr_cmd(0x8F); wr_d8(0xFF);
    wr_cmd(0xB6); wr_d8(0x00); wr_d8(0x00);
    wr_cmd(0x36); wr_d8(0x88);            /* MADCTL : identique au driver PAMI */
    wr_cmd(0x3A); wr_d8(0x05);            /* format pixel 16 bits */
    wr_cmd(0x90); wr_d8(0x08); wr_d8(0x08); wr_d8(0x08); wr_d8(0x08);
    wr_cmd(0xBD); wr_d8(0x06);
    wr_cmd(0xBC); wr_d8(0x00);
    wr_cmd(0xFF); wr_d8(0x60); wr_d8(0x01); wr_d8(0x04);
    wr_cmd(0xC3); wr_d8(0x13);
    wr_cmd(0xC4); wr_d8(0x13);
    wr_cmd(0xC9); wr_d8(0x22);
    wr_cmd(0xBE); wr_d8(0x11);
    wr_cmd(0xE1); wr_d8(0x10); wr_d8(0x0E);
    wr_cmd(0xDF); wr_d8(0x21); wr_d8(0x0C); wr_d8(0x02);
    wr_cmd(0xF0); wr_d8(0x45); wr_d8(0x09); wr_d8(0x08); wr_d8(0x08); wr_d8(0x26); wr_d8(0x2A);
    wr_cmd(0xF1); wr_d8(0x43); wr_d8(0x70); wr_d8(0x72); wr_d8(0x36); wr_d8(0x37); wr_d8(0x6F);
    wr_cmd(0xF2); wr_d8(0x45); wr_d8(0x09); wr_d8(0x08); wr_d8(0x08); wr_d8(0x26); wr_d8(0x2A);
    wr_cmd(0xF3); wr_d8(0x43); wr_d8(0x70); wr_d8(0x72); wr_d8(0x36); wr_d8(0x37); wr_d8(0x6F);
    wr_cmd(0xED); wr_d8(0x1B); wr_d8(0x0B);
    wr_cmd(0xAE); wr_d8(0x77);
    wr_cmd(0xCD); wr_d8(0x63);
    wr_cmd(0x70); wr_d8(0x07); wr_d8(0x07); wr_d8(0x04); wr_d8(0x0E); wr_d8(0x0F);
                  wr_d8(0x09); wr_d8(0x07); wr_d8(0x08); wr_d8(0x03);
    wr_cmd(0xE8); wr_d8(0x34);
    wr_cmd(0x62); wr_d8(0x18); wr_d8(0x0D); wr_d8(0x71); wr_d8(0xED); wr_d8(0x70); wr_d8(0x70);
                  wr_d8(0x18); wr_d8(0x0F); wr_d8(0x71); wr_d8(0xEF); wr_d8(0x70); wr_d8(0x70);
    wr_cmd(0x63); wr_d8(0x18); wr_d8(0x11); wr_d8(0x71); wr_d8(0xF1); wr_d8(0x70); wr_d8(0x70);
                  wr_d8(0x18); wr_d8(0x13); wr_d8(0x71); wr_d8(0xF3); wr_d8(0x70); wr_d8(0x70);
    wr_cmd(0x64); wr_d8(0x28); wr_d8(0x29); wr_d8(0xF1); wr_d8(0x01); wr_d8(0xF1); wr_d8(0x00); wr_d8(0x07);
    wr_cmd(0x66); wr_d8(0x3C); wr_d8(0x00); wr_d8(0xCD); wr_d8(0x67); wr_d8(0x45); wr_d8(0x45);
                  wr_d8(0x10); wr_d8(0x00); wr_d8(0x00); wr_d8(0x00);
    wr_cmd(0x67); wr_d8(0x00); wr_d8(0x3C); wr_d8(0x00); wr_d8(0x00); wr_d8(0x00); wr_d8(0x01);
                  wr_d8(0x54); wr_d8(0x10); wr_d8(0x32); wr_d8(0x98);
    wr_cmd(0x74); wr_d8(0x10); wr_d8(0x85); wr_d8(0x80); wr_d8(0x00); wr_d8(0x00); wr_d8(0x4E); wr_d8(0x00);
    wr_cmd(0x98); wr_d8(0x3E); wr_d8(0x07);
    wr_cmd(0x35);
    wr_cmd(0x21);
    wr_cmd(0x11); sleep_ms(120);
    wr_cmd(0x29); sleep_ms(20);
}
