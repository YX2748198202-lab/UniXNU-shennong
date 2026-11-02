// SPDX-License-Identifier: MIT
// Minimal board diagnostic screen.
//
// The full BootProgress.c needs the UFS/virtio/cpufreq/touch subsystems that this
// board does not build, so its archive cannot link here. What the bring-up needs is
// a stage marker: every boot_progress_stage() call paints one square straight into
// the kernel framebuffer mapping, so a photo of the screen counts how far the kernel
// got.
//
// Layout of the diagnostic screen (all sizes in framebuffer pixels):
//
//   top        green/blue/magenta bars painted by the earlier boot chains (not ours)
//   y = h/4    named-stage lane: one fixed square per named milestone, drawn the
//              first time its message arrives. Position and colour identify it, so
//              one photo shows exactly which milestones were passed:
//                 x=16   orange      arm_vm_init enter
//                 x=126  violet      arm_vm_init returned
//                 x=236  yellow      bsd_init enter
//                 x=346  dark orange original PMGR nub start
//                 x=456  lime        original PMGR nub returned
//                 x=566  magenta     vfs_mountroot enter
//                 x=676  red         vfs_mountroot mounted
//                 x=786  white       root authentication decision recorded
//                 x=896  cyan        load_init_program enter
//                 x=1006 teal        SystemOS mount enter
//                 x=1116 olive       Data mount enter
//                 x=1226 pink        temporary watchdog launch policy enter
//   y = h/2    generic event row: white/green alternating square for every stage
//              event, 30 per row, wrapping down (so a long run never leaves the
//              screen). Counting the squares here counts the events.
//   y = h/2+70 bsd_init print row: blue square for every "bsd_init: " print, which
//              is how the patched bsd_init_kprintf() reports progress. Separate row
//              keeps "inside bsd_init" measurable independently of the named lanes.
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
	uint32_t  named_seen;
} gScreen;

// No boot_progress_panic_text here on purpose: the panic-screen patcher compiles an
// extra copy loop into the screen when the symbol exists, which made the screen 7
// bytes larger than the padding it is placed in (0xa37 into 0xa30). The screen still
// draws the panic text; it just does not also store it for the live banner.

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

struct bp_named {
	const char *text;
	unsigned    x;
	uint32_t    colour;
};

// Order matters only for the on-screen x positions; the bit index is the array index.
static const struct bp_named bp_named_stages[] = {
	{ "arm_vm_init enter",                    16,   0xFFFFA500u },
	{ "arm_vm_init returned",                 126,  0xFF8A2BE2u },
	{ "bsd_init enter",                       236,  0xFFFFFF00u },
	{ "original PMGR nub start",              346,  0xFFFF8C00u },
	{ "original PMGR nub returned",           456,  0xFF32CD32u },
	{ "vfs_mountroot enter",                  566,  0xFFFF00FFu },
	{ "vfs_mountroot mounted",                676,  0xFFFF0000u },
	{ "root authentication decision recorded",786,  0xFFFFFFFFu },
	{ "load_init_program enter",              896,  0xFF00FFFFu },
	{ "SystemOS mount enter",                 1006, 0xFF008080u },
	{ "Data mount enter",                     1116, 0xFF808000u },
	{ "temporary watchdog launch policy enter",1226,0xFFFFC0CBu },
};

#define BP_NAMED_COUNT (sizeof(bp_named_stages) / sizeof(bp_named_stages[0]))
#define BP_ROW_SLOTS 30u
#define BP_MARKER 34u
#define BP_GAP 10u

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

static int bp_equal(const char *a, const char *b)
{
	if (a == 0 || b == 0) {
		return 0;
	}
	while (*a != '\0' && *a == *b) {
		++a;
		++b;
	}
	return *a == *b;
}

// Event square n, wrapped so a long run stays on screen: 30 per row.
static void bp_marker(unsigned n, unsigned base_y)
{
	unsigned row = n / BP_ROW_SLOTS;
	unsigned col = n % BP_ROW_SLOTS;
	unsigned x = 16 + col * (BP_MARKER + BP_GAP);
	unsigned y = base_y + row * (BP_MARKER + 16);
	uint32_t colour = (n & 1u) ? 0xFF00FF00u : 0xFFFFFFFFu;

	bp_rect(x, y, BP_MARKER, BP_MARKER, colour);
}

// Named-stage lane: one square per milestone, drawn once, position encodes identity.
static void bp_named(const char *text)
{
	unsigned i;

	if (!gScreen.bound) {
		return;
	}
	for (i = 0; i < BP_NAMED_COUNT; ++i) {
		if ((gScreen.named_seen & (1u << i)) != 0) {
			continue;
		}
		if (bp_equal(text, bp_named_stages[i].text) ||
		    bp_prefix(text, bp_named_stages[i].text)) {
			gScreen.named_seen |= 1u << i;
			bp_rect(bp_named_stages[i].x, gScreen.height / 4, 80, 80,
			    bp_named_stages[i].colour);
			return;
		}
	}
}

void boot_progress_init(void)
{
	gScreen.stages = 0;
	gScreen.bsd_prints = 0;
	gScreen.named_seen = 0;
}

void boot_progress_start(void)
{
	bp_marker(0, gScreen.height / 2);
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
	bp_named(text);
	if (bp_prefix(text, "bsd_init: ")) {
		bp_marker(gScreen.bsd_prints, gScreen.height / 2 + 70);
		++gScreen.bsd_prints;
	}
	bp_marker(++gScreen.stages, gScreen.height / 2);
}

void boot_progress_process_stage(int pid, const char *name, const char *text)
{
	(void)pid;
	(void)name;
	(void)text;
	bp_named(text);
	bp_marker(++gScreen.stages, gScreen.height / 2);
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
