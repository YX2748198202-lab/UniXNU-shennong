/* Standalone arm64e probe for the schema used by ucred.cr_label. */
#include <ptrauth.h>

#define KEY ptrauth_key_process_independent_data
#define DISC ptrauth_string_discriminator("ucred.cr_label")

#if SCHEMA == 1
#define QUAL __ptrauth(KEY, 1, DISC, "authenticates-null-values")
#elif SCHEMA == 0
#define QUAL __ptrauth(KEY, 1, DISC)
#elif SCHEMA == 2
/* Reference for testing the checker, never a compiler capability pass. */
#define QUAL
#else
#error unknown probe schema
#endif

struct slot {
    unsigned long prefix;
    void * QUAL value;
};

#if SCHEMA == 2
#define BLEND(s) ptrauth_blend_discriminator(&(s)->value, DISC)
#define LOAD(s) ptrauth_auth_data((s)->value, KEY, BLEND(s))
#define STORE(s, p) ((s)->value = ptrauth_sign_unauthenticated(p, KEY, BLEND(s)))
#else
#define LOAD(s) ((s)->value)
#define STORE(s, p) ((s)->value = (p))
#endif

void *probe_load(const struct slot *s) { return LOAD(s); }
void probe_store(struct slot *s, void *p) { STORE(s, p); }
void probe_clear(struct slot *s) { STORE(s, (void *)0); }

void probe_copy(struct slot *restrict dst, const struct slot *restrict src) {
#if SCHEMA == 2
    dst->value = ptrauth_auth_and_resign(src->value, KEY, BLEND(src), KEY, BLEND(dst));
#else
    dst->value = src->value;
#endif
}

extern void consume_slot(const struct slot *);
void probe_init(void) {
    struct slot s = {.prefix = 42, .value = (void *)0};
#if SCHEMA == 2
    STORE(&s, (void *)0);
#endif
    consume_slot(&s);
}
