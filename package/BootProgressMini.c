// SPDX-License-Identifier: MIT
// Minimal board diagnostic screen, v3: binary counters + named-stage lanes.
//
// The full BootProgress.c needs the UFS/virtio/cpufreq/touch subsystems that this
// board does not build, so its archive cannot link here. What the bring-up needs is
// an unambiguous marker: every boot_progress_stage() call paints into the kernel
// framebuffer mapping, and the screen spells the counts out in binary so a photo
// answers "how many events happened" exactly, without counting squares.
//
// Screen layout (framebuffer pixels, y grows downward; bands at the very top are
// painted by the earlier boot chains):
//
//   y = h/3       8 bits: number of boot_progress_stage() events   (bit0 at x=16,
//                 pitch 80, 60x60 squares; white = 1, dark grey = 0)
//   y = h/3+100   8 bits: number of "bsd_init: " print events
//   y = h/3+220   named lane 1: the 12 board milestone markers, fixed colour+slot
//   y = h/3+320   named lane 2: 12 early-startup milestone markers
//   y = h/2       event row: one white/green square per event, 30 per row, wrapping
//
// A photo therefore gives: exact event count (binary), exact bsd_init print count
// (binary), which board milestones were passed (coloured lane 1) and which early
// startup milestones were passed (coloured lane 2).
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
	unsigned  bsd_prints;
	unsigned  named_seen;
	unsigned  named_seen2;
} gScreen;

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

// Lane 1: board milestones added by the boot-progress patch.
static const char *const bp_lane1[] = {
	"arm_vm_init enter",
	"arm_vm_init returned",
	"bsd_init enter",
	"original PMGR nub start",
	"original PMGR nub returned",
	"vfs_mountroot enter",
	"vfs_mountroot mounted",
	"root authentication decision recorded",
	"load_init_program enter",
	"SystemOS mount enter",
	"Data mount enter",
	"temporary watchdog launch policy enter",
};

// Lane 2: early startup messages from kernel_bootstrap()/kernel_bootstrap_thread().
static const char *const bp_lane2[] = {
	"vm_mem_bootstrap",
	"console_init",
	"machine_init",
	"clock_init",
	"code_signing_init",
	"thread_init",
	"workq_init",
	"exception_init",
	"kernel_thread_create",
	"idle_thread_create",
	"sched_startup",
	"clock_service_create",
};

static const uint32_t bp_lane1_colour[] = {
	0xFFFFA500u,	// orange      arm_vm_init enter
	0xFF8A2BE2u,	// violet      arm_vm_init returned
	0xFFFFFF00u,	// yellow      bsd_init enter
	0xFFFF8C00u,	// dark orange PMGR start
	0xFF32CD32u,	// lime        PMGR returned
	0xFFFF00FFu,	// magenta     vfs_mountroot enter
	0xFFFF0000u,	// red         vfs_mountroot mounted
	0xFFFFFFFFu,	// white       root auth recorded
	0xFF00FFFFu,	// cyan        load_init_program enter
	0xFF008080u,	// teal        SystemOS mount enter
	0xFF808000u,	// olive       Data mount enter
	0xFFFFC0CBu,	// pink        watchdog policy enter
};

static const uint32_t bp_lane2_colour[] = {
	0xFFFFFFFFu,	// white
	0xFF00FF00u,	// green
	0xFFFFFF00u,	// yellow
	0xFFFF8C00u,	// dark orange
	0xFFFF00FFu,	// magenta
	0xFF00FFFFu,	// cyan
	0xFF32CD32u,	// lime
	0xFF8A2BE2u,	// violet
	0xFFFF0000u,	// red
	0xFF008080u,	// teal
	0xFF808000u,	// olive
	0xFFFFA500u,	// orange
};

#define BP_LANE1_COUNT (sizeof(bp_lane1) / sizeof(bp_lane1[0]))
#define BP_LANE2_COUNT (sizeof(bp_lane2) / sizeof(bp_lane2[0]))
#define BP_ROW_SLOTS 30u
#define BP_MARKER 34u
#define BP_GAP 10u
#define BP_BITS 8u
#define BP_DIM 0xFF303030u

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

static int bp_prefix(const char *text, const char *prefix)
{
	if (text == 0 || prefix == 0) {
		return 0;
	}
	while (*prefix != '\0') {
		if (*text != *prefix) {
			return 0;
		}
		++text;
		++prefix;
	}
	return 1;
}

// Eight squares spell a count in binary: bit0 leftmost, white = 1, dark grey = 0.
static void bp_bits(unsigned value, unsigned y)
{
	unsigned i;

	for (i = 0; i < BP_BITS; ++i) {
		uint32_t colour = ((value >> i) & 1u) ? 0xFFFFFFFFu : BP_DIM;
		bp_rect(16 + i * 80, y, 60, 60, colour);
	}
}

static void bp_marker(unsigned n)
{
	unsigned row = n / BP_ROW_SLOTS;
	unsigned col = n % BP_ROW_SLOTS;
	unsigned x = 16 + col * (BP_MARKER + BP_GAP);
	unsigned y = gScreen.height / 2 + row * (BP_MARKER + 16);
	uint32_t colour = (n & 1u) ? 0xFF00FF00u : 0xFFFFFFFFu;

	bp_rect(x, y, BP_MARKER, BP_MARKER, colour);
}

static void bp_lane(const char *text, const char *const *names, const uint32_t *colours,
    unsigned count, unsigned *seen, unsigned y)
{
	unsigned i;

	if (!gScreen.bound) {
		return;
	}
	for (i = 0; i < count; ++i) {
		if ((*seen & (1u << i)) != 0) {
			continue;
		}
		if (bp_prefix(text, names[i])) {
			*seen |= 1u << i;
			bp_rect(16 + i * 94, y, 56, 56, colours[i]);
			return;
		}
	}
}

void boot_progress_init(void)
{
	gScreen.stages = 0;
	gScreen.bsd_prints = 0;
	gScreen.named_seen = 0;
	gScreen.named_seen2 = 0;
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
	bp_lane(text, bp_lane1, bp_lane1_colour, BP_LANE1_COUNT, &gScreen.named_seen,
	    gScreen.height / 3 + 220);
	bp_lane(text, bp_lane2, bp_lane2_colour, BP_LANE2_COUNT, &gScreen.named_seen2,
	    gScreen.height / 3 + 320);
	if (bp_prefix(text, "bsd_init: ")) {
		++gScreen.bsd_prints;
		bp_bits(gScreen.bsd_prints, gScreen.height / 3 + 100);
	}
	bp_marker(++gScreen.stages);
	bp_bits(gScreen.stages, gScreen.height / 3);
}

void boot_progress_process_stage(int pid, const char *name, const char *text)
{
	(void)pid;
	(void)name;
	bp_lane(text, bp_lane1, bp_lane1_colour, BP_LANE1_COUNT, &gScreen.named_seen,
	    gScreen.height / 3 + 220);
	bp_lane(text, bp_lane2, bp_lane2_colour, BP_LANE2_COUNT, &gScreen.named_seen2,
	    gScreen.height / 3 + 320);
	bp_marker(++gScreen.stages);
	bp_bits(gScreen.stages, gScreen.height / 3);
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
