// SPDX-License-Identifier: MIT
// Minimal board diagnostic screen.
//
// The full BootProgress.c needs the UFS/virtio/cpufreq/touch subsystems that this
// board does not build, so its archive cannot link here. What the bring-up needs
// first is only a stage marker: one square per boot_progress_stage() call, painted
// straight into the kernel's framebuffer mapping. Counting the squares in a photo
// tells how far the kernel got, which is the whole question while the /cpus hang is
// being chased.
//
// No kernel headers are used: boot_progress_bind() already receives the geometry.

#include <stdint.h>

typedef unsigned long bp_ulong;

static struct {
	uintptr_t base;
	unsigned  width;
	unsigned  height;
	unsigned  rowbytes;
	unsigned  depth;
	int       bound;
	unsigned  stages;
} gScreen;

// The panic screen patcher resolves this symbol to copy the formatted panic text
// into it; keep the name and the size.
char boot_progress_panic_text[2048];

void boot_progress_init(void);
void boot_progress_start(void);
int  boot_progress_active(void);
void boot_progress_bind(uintptr_t, unsigned, unsigned, unsigned, unsigned);
void boot_progress_putc(char);
void boot_progress_stage(const char *);
void boot_progress_irq(uint64_t, uint64_t, uint64_t);
void boot_progress_poll(void);
void boot_progress_user_breakpoint(void *, unsigned);
void boot_progress_user_abort(void *, unsigned, uint64_t);
void boot_progress_critical_exit(int, char *, bp_ulong);
void boot_progress_process_stage(int, const char *, const char *);
void boot_progress_exit(int, const char *, int, unsigned, uint64_t);

static void bp_pixel(unsigned x, unsigned y, uint32_t colour)
{
	volatile uint32_t *at;

	if (!gScreen.bound || x >= gScreen.width || y >= gScreen.height) {
		return;
	}
	at = (volatile uint32_t *)(gScreen.base + (uint64_t)y * gScreen.rowbytes + (uint64_t)x * 4);
	*at = colour;
}

static void bp_rect(unsigned x0, unsigned y0, unsigned w, unsigned h, uint32_t colour)
{
	unsigned x, y;

	for (y = 0; y < h; ++y) {
		for (x = 0; x < w; ++x) {
			bp_pixel(x0 + x, y0 + y, colour);
		}
	}
}

// Square n: white for odd stages, green for even ones, so two adjacent squares
// are always distinguishable on a photographed screen.
static void bp_marker(unsigned n)
{
	unsigned size = 34, gap = 10;
	unsigned x = 16 + n * (size + gap);
	unsigned y;

	if (!gScreen.bound) {
		return;
	}
	y = gScreen.height / 2;
	bp_rect(x, y, size, size, (n & 1u) ? 0xFF00FF00u : 0xFFFFFFFFu);
}

void boot_progress_init(void)
{
	gScreen.stages = 0;
}

void boot_progress_start(void)
{
	bp_marker(0);
}

int boot_progress_active(void)
{
	return gScreen.bound;
}

void boot_progress_bind(uintptr_t base, unsigned w, unsigned h, unsigned rb, unsigned depth)
{
	if (base == 0 || depth != 32 || w < 64 || h < 64 || rb < w * 4) {
		return;
	}
	gScreen.base = base;
	gScreen.width = w;
	gScreen.height = h;
	gScreen.rowbytes = rb;
	gScreen.depth = depth;
	gScreen.bound = 1;
	// Red corner: proof that the kernel bound the framebuffer and this screen is drawing.
	bp_rect(8, 8, 48, 48, 0xFFFF0000u);
}

void boot_progress_putc(char c)
{
	(void)c;
}

void boot_progress_stage(const char *text)
{
	(void)text;
	++gScreen.stages;
	bp_marker(gScreen.stages);
}

void boot_progress_process_stage(int pid, const char *name, const char *text)
{
	(void)pid;
	(void)name;
	(void)text;
	++gScreen.stages;
	bp_marker(gScreen.stages);
}

void boot_progress_irq(uint64_t a, uint64_t b, uint64_t c)
{
	(void)a;
	(void)b;
	(void)c;
}

void boot_progress_poll(void)
{
}

void boot_progress_user_breakpoint(void *a, unsigned b)
{
	(void)a;
	(void)b;
}

void boot_progress_user_abort(void *a, unsigned b, uint64_t c)
{
	(void)a;
	(void)b;
	(void)c;
}

void boot_progress_critical_exit(int a, char *b, bp_ulong c)
{
	(void)a;
	(void)b;
	(void)c;
}

void boot_progress_exit(int a, const char *b, int c, unsigned d, uint64_t e)
{
	(void)a;
	(void)b;
	(void)c;
	(void)d;
	(void)e;
}
