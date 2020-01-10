picoblaze_utils
===============

picoblaze c-compiler and assembly and linker writing in python.


This is easy assembly like c style, not really c!

Edit, by PSA: To be clear, this is DEFINITELY not C, it's just
more readable than assembly, and the C preprocessor is
more powerful than the KCPSM assembler. Don't do anything other
than basic operations or tests: that is, if (a < b), not
if ( (a + b) < c). Basically, just think in your head - is this
going to need to create a temporary? If so, it won't work.
That's what a compiler is for.

PicoBlaze (like most processors) only has 2-operand operations,
so keep that in mind: don't do "A = B + C", that's a 3-operand
operation (don't even do "A = A + B", do "A += B"). Yes, it would
be easy to eventually parse this, no, I don't know if I'll do it.

Added a symbol to fill out what can be done. First, added
multi-operand operations for registers. Literally any number
of registers can combine so something like
```
sA.sB = 0x1000;
```
with the registers ordered MSB-first. This works for all
operations (add/subtract/compare/bitwise), including `sA.sB += sC.sD`.
Pointless bitwise operations will be trimmed, so `sA.sB |= 0x1000;`
will be trimmed to `sA |= 0x10`.

**No for loops.** Yes, this is kinda annoying, but that's
not an easy syntax to translate. No structs, unions, classes,
or variables. Again, it's really just assembly, just in a more
familiar syntax.

# Compare (if/while/dowhile) operations

Simple comparisons are supported, not compound operations. Comparisons
can also be negated, as in `if (!(s0 & 0x80))`, however this is only
for readability, as there's a complement for every operator in C.

## Comparison operations

All of `<`,`>`,`<=`,`>=`,`==`, and `!=` are supported, with either
constants or registers, but the register needs to come first. Constant
math also works, so `if (s0 < (3 + 4)` is fine.

## Bitwise operations

Only `&` and `^` are supported as comparison operations, since they
correspond to `test`/`testcy`, with `s0 ^ s1` equivalent to `!(s0 & s1)`.
(obviously if s0 XOR s1 == 0, s0 = ~s1, and s0 & ~s0 = 0).

## Arithmetic tests

Right now `--s0`/`s0--` is the only operator you can merge into a test
(so you CANNOT do `if (s0 -= 4)`, although I may add this later.
You will **never** be able to do `if (s0 - 4)`, because that requires
the creation of a temporary.

Loops are most efficient if you use `do..while` syntax, although simple
delay loops (e.g. `while (s0--);`) are just as efficient. This is
because with `do..while` there's just a single compare/test/etc.
and jump operation at the end, whereas `while` has a compare/test
and jump at the beginning, and then a jump at the end of the loop
to go back.

Keep in mind the difference between a prefix/postfix operator: `--s0`
tests to see if `s0` is zero after subtract, `s0--` tests to see if `s0`
is zero before subtract (which means it's -1 afterwards).

## Z and C flags

You can use the Z and C flags in a compare operation and test against
zero (i.e. if (Z == 0) or if (Z != 0)). This is useful in combination
with the ``psm()`` intrinsic function which can help to make it clear
that you're doing something sneaky.

# Debugging symbols

pblaze-ld.py generates debugging symbols inside the final HDL output,
so in a simulation if you look inside the scope of the ROM, there will
be a "dbg_instr" element which if you change the radix to ASCII,
while decode where the program is. Another helpful debugging tip is
to use the PicoBlaze "stack_pointer" debugging object and convert
its radix to analog. This helps to visualize very quickly where the
program is switching functions. 

You can use macro, this python depend on mcpp(preprocessor) and astyle(style formater).

mcpp: http://mcpp.sourceforge.net/

astyle: http://astyle.sourceforge.net/


```c
#define r_io s0
bool_t isr_test(void) __attribute__((interrupt ("IRQ0")));

bool_t isr_test(void)
{
    r_io = 0x00;
    output(0xFF, &r_io);
    return true;
}

void init(void)
{
    while (s0 == s0) {
        s0 = s0;
    }
}
```

pblaze-cc.py will generate this assembly.

```asm
;------------------------------------------------------------
address 0x000
boot:
  call init
loop:
  jump loop

;------------------------------------------------------------
;D:/Work/Checkout.Git/picoblaze_utils/test.c
init:
 L_f512cca69f269d9d7abd0a0f2e96a5f4_0:
 ;D:/Work/Checkout.Git/picoblaze_utils/test.c:12
  ;void init (void)

 L_f512cca69f269d9d7abd0a0f2e96a5f4_1:
 ;D:/Work/Checkout.Git/picoblaze_utils/test.c:14
    ;while (s0 == s0), L_f512cca69f269d9d7abd0a0f2e96a5f4_2, JOIN_0
    compare s0, s0
    jump NZ, JOIN_0

 L_f512cca69f269d9d7abd0a0f2e96a5f4_2:
 ;D:/Work/Checkout.Git/picoblaze_utils/test.c:15
        move s0, s0

 JOIN_2:
 ;D:/Work/Checkout.Git/picoblaze_utils/test.c:14
    ;endwhile
    jump L_f512cca69f269d9d7abd0a0f2e96a5f4_1

 JOIN_0:
 ;D:/Work/Checkout.Git/picoblaze_utils/test.c:12
  ;endfunc

_end_init:
  return


;------------------------------------------------------------
;D:/Work/Checkout.Git/picoblaze_utils/test.c
isr_test:
 L_f512cca69f269d9d7abd0a0f2e96a5f4_3:
 ;D:/Work/Checkout.Git/picoblaze_utils/test.c:5
  ;bool_t isr_test (void)

 L_f512cca69f269d9d7abd0a0f2e96a5f4_4:
 ;D:/Work/Checkout.Git/picoblaze_utils/test.c:7
    move s0, 0
 ;D:/Work/Checkout.Git/picoblaze_utils/test.c:8
    output s0, 255
 ;D:/Work/Checkout.Git/picoblaze_utils/test.c:9
    returni enable

 JOIN_1:
 ;D:/Work/Checkout.Git/picoblaze_utils/test.c:5
  ;endfunc

_end_isr_test:
  returni enable



;ISR
address 0x3F0
jump    isr_test
```

pblaze-as.py will convert to obj.

```json
{
    "labels": {
        "L_f512cca69f269d9d7abd0a0f2e96a5f4_1": 2, 
        "L_f512cca69f269d9d7abd0a0f2e96a5f4_0": 2, 
        "_end_init": 6, 
        "L_f512cca69f269d9d7abd0a0f2e96a5f4_2": 4, 
        "isr_test": 7, 
        "JOIN_2": 5, 
        "JOIN_1": 10, 
        "JOIN_0": 6, 
        "boot": 0, 
        "L_f512cca69f269d9d7abd0a0f2e96a5f4_3": 7, 
        "init": 2, 
        "_end_isr_test": 10, 
        "loop": 1, 
        "L_f512cca69f269d9d7abd0a0f2e96a5f4_4": 7
    }, 
    "ctime": "Thu Jul 11 00:01:32 2013", 
    "object": [
        196610, 
        212993, 
        86016, 
        218118, 
        4096, 
        212994, 
        172032, 
        0, 
        180479, 
        229377, 
        229377, 
        0, 
        "......",
        0, 
        212999
    ], 
    "mtime": "Thu Jul 11 00:01:32 2013"
}
```

then pblaze-ld.py convert to verilog.
```verilog
/*
 * source : test.s
 * create : Thu Jul 11 00:01:32 2013
 * modify : Thu Jul 11 00:01:32 2013
 */
`timescale 1 ps / 1ps
module test (address, instruction, clk);
input [9:0] address;
input clk;
output [17:0] instruction;

RAMB16_S18 #(
    .INIT(18'h00000),

    // The following INIT_xx declarations specify the initial contents of the RAM
    // Address 0 to 255
    .INIT_00(256'h0000000000000000000080018001C0FF0000A000400210005406500040010002),
    .INIT_01(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_02(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_03(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_04(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_05(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_06(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_07(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_08(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_09(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_0A(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_0B(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_0C(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_0D(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_0E(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_0F(256'h0000000000000000000000000000000000000000000000000000000000000000),

    // Address 256 to 511
    .INIT_10(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_11(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_12(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_13(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_14(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_15(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_16(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_17(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_18(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_19(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_1A(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_1B(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_1C(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_1D(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_1E(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_1F(256'h0000000000000000000000000000000000000000000000000000000000000000),

    // Address 512 to 767
    .INIT_20(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_21(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_22(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_23(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_24(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_25(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_26(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_27(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_28(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_29(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_2A(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_2B(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_2C(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_2D(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_2E(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_2F(256'h0000000000000000000000000000000000000000000000000000000000000000),

    // Address 768 to 1023
    .INIT_30(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_31(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_32(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_33(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_34(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_35(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_36(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_37(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_38(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_39(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_3A(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_3B(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_3C(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_3D(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_3E(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INIT_3F(256'h0000000000000000000000000000000000000000000000000000000000004007),

    // The next set of INITP_xx are for the parity bits
    // Address 0 to 255
    .INITP_00(256'h00000000000000000000000000000000000000000000000000000000003E2CDF),
    .INITP_01(256'h0000000000000000000000000000000000000000000000000000000000000000),

    // Address 256 to 511
    .INITP_02(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INITP_03(256'h0000000000000000000000000000000000000000000000000000000000000000),

    // Address 512 to 767
    .INITP_04(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INITP_05(256'h0000000000000000000000000000000000000000000000000000000000000000),

    // Address 768 to 1023
    .INITP_06(256'h0000000000000000000000000000000000000000000000000000000000000000),
    .INITP_07(256'h0000000300000000000000000000000000000000000000000000000000000000),

    // Output value upon SSR assertion
    .SRVAL(18'h000000),
    .WRITE_MODE("WRITE_FIRST")
) ram_1024_x_18(
    .DI  (16'h0000),
    .DIP  (2'b00),
    .EN (1'b1),
    .WE (1'b0),
    .SSR (1'b0),
    .CLK (clk),
    .ADDR (address),
    .DO (instruction[15:0]),
    .DOP (instruction[17:16])
);

endmodule
```



I am still learning llvm, so this tools maybe rewrite to llvm later.
