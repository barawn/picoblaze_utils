#include "kcpsm6.h"
#define r_io s0
bool_t isr_test(void) __attribute__ ((interrupt ("IRQ0")));

bool_t isr_test(void)
{
    r_io = 0x00;
    output(0xFF, &r_io);
    if (!(r_io & 0x1)) {
      r_io |= 0x1;
    }
    return true;
}

void init(void)
{
    while (s0 == s0) {
        s0 = s0;
    }
}

