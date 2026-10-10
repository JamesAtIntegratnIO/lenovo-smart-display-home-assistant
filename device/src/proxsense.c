/* proxsense: watch the display's proximity sensor and say when someone comes close.
 *
 * The sensor is a VCNL4200 on I2C bus 2, address 0x51: an infrared LED and a photodiode
 * behind the bezel, next to the ambient light sensor. Android Things drives the chip from
 * user space (no kernel driver, nothing in /sys) and leaves the proximity half switched off,
 * and the display has no i2c tools, hence this program. It only touches the proximity
 * registers; the light sensor that auto-brightness uses is left alone.
 *
 *   proxsense raw          print the reading five times a second (to choose DELTA)
 *   proxsense DELTA        print "near COUNTS REST" when the reading rises DELTA above its
 *                          resting level, and again every REPEAT seconds while it stays there
 *
 * The resting level (reflection from the bezel, about 38 here) is tracked slowly while
 * nobody is near, and something left in front of the display becomes the new resting level
 * after ADOPT seconds, so a bowl on the counter cannot hold it "near" for ever.
 *
 * Build (static, 32-bit ARM), on the computer:
 *   nix shell nixpkgs#zig -c zig cc -target arm-linux-musleabihf -static -Os -s -o proxsense device/src/proxsense.c
 */
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/i2c.h>
#include <linux/i2c-dev.h>

#define BUS "/dev/i2c-2"
#define ADDR 0x51
#define PS_CONF12 0x03
#define PS_CONF3_MS 0x04
#define PS_DATA 0x08
/* Longest reach the chip offers: 9T integration, 16-bit output, 8 pulses, 200 mA LED (1/160 duty). */
#define CONF12 0x080a
#define CONF3_MS 0x0760
#define REPEAT 30   /* seconds between reports while someone stays near */
#define ADOPT 120   /* seconds after which whatever is in front counts as furniture */

static int fd;

static int reg(int r, int value) {   /* value < 0: read */
    unsigned char buf[3] = {r, value & 0xff, (value >> 8) & 0xff};
    struct i2c_msg m[2] = {{ADDR, 0, value < 0 ? 1 : 3, buf}, {ADDR, I2C_M_RD, 2, buf + 1}};
    struct i2c_rdwr_ioctl_data x = {m, value < 0 ? 2 : 1};
    if (ioctl(fd, I2C_RDWR, &x) < 0) return -1;
    return buf[1] | buf[2] << 8;
}

int main(int argc, char **argv) {
    if (argc != 2) { fprintf(stderr, "usage: proxsense raw | DELTA\n"); return 2; }
    int raw = !strcmp(argv[1], "raw"), delta = atoi(argv[1]);
    if (!raw && delta <= 0) { fprintf(stderr, "DELTA must be a positive number\n"); return 2; }
    if ((fd = open(BUS, O_RDWR)) < 0) { perror(BUS); return 1; }
    setvbuf(stdout, 0, _IOLBF, 0);

    int rest16 = -1, above = 0, near_ticks = 0, since = 0, tick = 0;   /* rest16: resting level x16 */
    for (;; tick++) {
        if (tick % 300 == 0 && reg(PS_CONF12, -1) != CONF12) {   /* at start, and if anything resets the chip */
            reg(PS_CONF3_MS, CONF3_MS);
            reg(PS_CONF12, CONF12);
            usleep(1000000);
        }
        int v = reg(PS_DATA, -1);
        usleep(200000);
        if (v < 0) continue;
        if (raw) { printf("%d\n", v); continue; }
        if (rest16 < 0) rest16 = v * 16;
        if (v * 16 > rest16 + delta * 16) {
            above++; near_ticks++;
            if (near_ticks > ADOPT * 5) { rest16 = v * 16; above = near_ticks = 0; continue; }
            if (above >= 2 && (above == 2 || ++since >= REPEAT * 5)) {   /* two readings in a row: not a glitch */
                printf("near %d %d\n", v, rest16 / 16);
                since = 0;
            }
        } else {
            above = near_ticks = since = 0;
            rest16 += (v * 16 - rest16) / 64;   /* follows drift over ten seconds or so */
        }
    }
}
