/* Freestanding terminal-fault renderer. No thread, allocator, PAC callback or incoming stack. */
#include "fatal-record.h"
#include "Font.h"
static const u64 font[] = GLYPH_FONT
extern u8 fatal_log[];
extern const u64 fatal_video_state[], fatal_fb_root[];
struct screen {struct fatal_video v; u32 x,y,n;};
__attribute__((noreturn)) static void park(void) {for(;;)__asm__ volatile("wfe");}
static u64 par(u64 va,int write) {
  u64 p;
  if(write)__asm__ volatile("at s1e1w,%0"::"r"(va):"memory");
  else __asm__ volatile("at s1e1r,%0"::"r"(va):"memory");
  __asm__ volatile("isb\n mrs %0,par_el1":"=r"(p)::"memory");return p;
}
static u64 sctlr(void){u64 r;__asm__ volatile("mrs %0,sctlr_el1":"=r"(r));return r;}
static int readable(u64 va,u64 bytes) {
  if(!bytes || va+bytes<va)return 0;
  if(!(sctlr()&1))return va>=0x80000000UL && va+bytes<=0x4000000000UL;
  if(par(va,0)&1 || par(va+bytes-1,0)&1)return 0;
  for(u64 p=(va&~4095UL)+4096;p<va+bytes;p+=4096)if(par(p,0)&1)return 0;
  return 1;
}
static void flush(struct screen *g) {
  u64 start=g->v.base+(g->y<g->v.h?g->y:0)*g->v.rb;
  u64 end=start+42*g->v.rb,limit=g->v.base+g->v.rb*g->v.h;
  if(end>limit)end=limit;
  for(u64 a=start&~63UL;a<end;a+=64)__asm__ volatile("dc civac,%0"::"r"(a):"memory");
  __asm__ volatile("dsb sy":::"memory");
}
static void put(struct screen *g,u8 c) {
  /* Byte 2047 is the first-panic claim. Never overwrite it, even with NUL. */
  if(g->n<2046 && c>=9 && c<=126){fatal_log[g->n++]=c;fatal_log[g->n]=0;}
  if(c=='\n'){flush(g);g->x=0;g->y+=42;return;}
  if(c<32 || c>126)return;
  if(g->x+18>g->v.w){flush(g);g->x=0;g->y+=42;}
  if(g->y+42>g->v.h)return;
  u64 glyph=font[c-32];
  for(u32 row=0;row<12;row++){
    u32 bits=row<6?(u32)(glyph>>32)>>(row*5):(u32)glyph>>((row-6)*5);
    for(u32 col=0;col<5;col++)if((bits>>col)&1)
      for(u32 dy=0;dy<3;dy++)for(u32 dx=0;dx<3;dx++)
        *(volatile u32 *)(g->v.base+(g->y+row*3+dy)*g->v.rb+(g->x+col*3+dx)*4)=0xffffffff;
  }
  g->x+=18;
}
static void text(struct screen *g,const char *s){for(u32 n=0;n<256 && readable((u64)s+n,1) && s[n];n++)put(g,s[n]);}
static void number(struct screen *g,u64 n,u32 base,u32 width){
  u8 digits[24];u32 count=0;
  do{u32 d=n%base;digits[count++]="0123456789abcdef"[d];n/=base;}while(n && count<24);
  while(width>count){put(g,'0');width--;}
  while(count)put(g,digits[--count]);
}
static void field(struct screen *g,const char *name,u64 value){text(g,name);text(g,"=0x");number(g,value,16,16);put(g,'\n');}
/* Bounded Darwin ARM64 stack-slot formatter. No unprobed fmt/argument/string reads. */
static void format(struct screen *g,const char *fmt,const u64 *args){
  u32 used=0;
  for(u32 i=0;i<512 && readable((u64)fmt+i,1) && fmt[i];i++){
    u8 c=fmt[i];if(c!='%'){put(g,c);continue;}
    u32 width=0;
    do {i++;if(i>=512 || !readable((u64)fmt+i,1))return;c=fmt[i];
      if(c>='0' && c<='9' && width<16)width=width*10+c-'0';
    }while((c>='0'&&c<='9') || c=='l' || c=='z' || c=='-' || c=='.');
    if(c=='%'){put(g,c);continue;}
    if(used>=48 || !readable((u64)(args+used),8)){text(g,"[bad args]");return;}
    u64 v=args[used++];if(width>16)width=16;
    if(c=='s')text(g,(const char *)v);
    else if(c=='c')put(g,(u8)v);
    else if(c=='p'||c=='x'||c=='X')number(g,v,16,c=='p'?16:width);
    else if(c=='u'||c=='d'||c=='i')number(g,v,10,width);
    else {put(g,'%');put(g,c);}
  }
}
static int setup(struct screen *g,volatile struct fatal_record *r){
  const u64 *v;u64 bytes;
  if(r->source>=16){
    if((r->arg0&7) || !readable(r->arg0,0x58))return 0;
    v=(const u64 *)(r->arg0+0x28);
    g->v=(struct fatal_video){v[0],v[2],v[3],v[4],v[5]};
  } else {
    v=fatal_video_state;if(!readable((u64)v,40))return 0;
    g->v=(struct fatal_video){v[0]&~3UL,v[1],v[2],v[3],v[4]};
  }
  if(!fatal_video_valid(g->v))return 0;r->status=2;bytes=g->v.rb*g->v.h;
  if(sctlr()&1){
    /* A physical low-vector PC/stack must not lose its own TTBR0 mapping. */
    if(r->source>=16){
      for(u64 at=g->v.base;at<g->v.base+bytes;at+=4096)if(par(at,1)&1)return 0;
      if(par(g->v.base+bytes-1,1)&1)return 0;
      goto mapped;
    }
    /* Only the observed 3..4GiB framebuffer block can get a private fatal view. */
    if((g->v.base>>30)!=3 || ((g->v.base+bytes-1)>>30)!=3 || ((r->mair>>24)&~13UL &255))return 0;
    u64 pa=par((u64)fatal_fb_root,0);if(pa&1)return 0;pa&=0x0000fffffffff000UL;
    u64 tcr=(r->tcr&~0xffffUL)|25UL|(1UL<<8)|(1UL<<10)|(3UL<<12);
    __asm__ volatile("dsb ish\n msr ttbr0_el1,%0\n msr tcr_el1,%1\n isb\n tlbi vmalle1is\n dsb ish\n isb"::"r"(pa),"r"(tcr):"memory");
    for(u64 at=g->v.base;at<g->v.base+bytes;at+=4096)if(par(at,1)&1)return 0;
    if(par(g->v.base+bytes-1,1)&1)return 0;
  }
mapped:
  r->status=3;g->x=0;g->y=g->v.h/8;g->n=0;return 1;
}
__attribute__((noreturn)) void fatal_main(volatile struct fatal_record *r){
  struct screen g;
  if(!setup(&g,r)){r->status=0xe1;__asm__ volatile("dsb sy");park();}
  for(u64 y=g.y;y<g.v.h;y++)for(u64 x=0;x<g.v.w;x++)
    *(volatile u32 *)(g.v.base+y*g.v.rb+x*4)=0;
  text(&g,"fi138 / full checks / fatal record\n");
  field(&g,"source",r->source);
  if(r->source==3){
    struct fatal_state s;
    if(readable(r->arg1,0x128) && fatal_state_decode((const void *)r->arg1,0x128,&s)){
      text(&g,"ORIGINAL saved_state\n");field(&g,"PC",s.pc);field(&g,"LR",s.lr);field(&g,"SP",s.sp);
      field(&g,"ESR",s.esr);field(&g,"FAR",s.far);field(&g,"CPSR",s.cpsr);
    }else {text(&g,"INVALID saved_state\n");field(&g,"state",r->arg1);}
  }else{
    text(&g,r->source>=4?"HARDWARE exception registers\n":"PANIC entry / ELR may be stale\n");
    field(&g,"ELR",r->elr);field(&g,"LR",r->lr);field(&g,"SP",r->sp);
    field(&g,"ESR",r->esr);field(&g,"FAR",r->far);field(&g,"SPSR",r->spsr);
  }
  r->status=4;
  field(&g,"SCTLR",r->sctlr);field(&g,"TCR",r->tcr);field(&g,"TTBR0",r->ttbr0);
  field(&g,"TTBR1",r->ttbr1);field(&g,"MAIR",r->mair);field(&g,"VBAR",r->vbar);
  field(&g,"CurrentEL",r->current_el);field(&g,"nested",r->nested);
  if(r->source<4){
    const u64 *args=(const u64 *)r->arg1;
    if(r->source==2){if(readable((u64)args,8))args=(const u64 *)*args;else args=0;}
    if(r->source==3)text(&g,(const char *)r->arg0);
    else format(&g,(const char *)r->arg0,args);
  }
  put(&g,'\n');r->status=5;__asm__ volatile("dsb sy":::"memory");park();
}
