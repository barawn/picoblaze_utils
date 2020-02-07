#!/usr/bin/env python2
# -*- coding:utf-8 -*-
#  
#  Copyright 2013 buaa.byl@gmail.com
#
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2, or (at your option)
#  any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; see the file COPYING.  If not, write to
#  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
#
#
# 2013.08.12    first release
#
import os
import sys
import json
import getopt
import re
from mako.template import Template

dualport = False

# sigh, this is big
tpl_oneport = '''\
`timescale 1 ps / 1ps

/* 
 * == pblaze-as ==
 * source : ${project}.s
 * create : ${ctime}
 * modify : ${mtime}
 */
/* 
 * == pblaze-ld ==
 * target : kcpsm3
 */

module ${project} (address, instruction, enable, clk, rdl);
parameter USE_JTAG_LOADER = "FALSE";
localparam BRAM_PORT_WIDTH = 18;
localparam BRAM_ADR_WIDTH = (BRAM_PORT_WIDTH == 18) ? 10 : 11;
localparam BRAM_WE_WIDTH = (BRAM_PORT_WIDTH == 18) ? 2 : 1;
input [9:0] address;
input clk;
input enable;
output [17:0] instruction;
output rdl; // download reset

wire [BRAM_ADR_WIDTH-1:0] jtag_addr;
wire jtag_we;
wire jtag_clk;
wire [17:0] jtag_din;
wire [17:0] bram_macro_din;
wire [17:0] jtag_dout;
wire [17:0] bram_macro_dout;
wire jtag_en;

// Note: JTAG loader's DIN goes to (15:0) DIBDI and (17:16) DIPBDIP.
// Because we use the TDP macro, the parity is interspersed every byte,
// meaning we need to swizzle it to
// { jtag_din[17],jtag_din[8 +: 8],jtag_din[16],jtag_din[0 +: 8] }
// and when going back, we need to do
// { bram_macro_dout[17], bram_macro_dout[8], bram_macro_dout[9 +: 8], bram_macro_dout[0 +: 8] }
assign bram_macro_din = { jtag_din[17], jtag_din[8 +: 8],    // byte 1
                          jtag_din[16], jtag_din[0 +: 8] };  // byte 0
assign jtag_dout = { bram_macro_dout[17], bram_macro_dout[8],            // parity
                     bram_macro_dout[9 +: 8], bram_macro_dout[0 +: 8] }; // data

generate
  if (USE_JTAG_LOADER == "YES" || USE_JTAG_LOADER == "TRUE") begin : JL
     jtag_loader_6 #(.C_JTAG_LOADER_ENABLE(1),
                     .C_FAMILY("7S"),
                     .C_NUM_PICOBLAZE(1),
                     .C_BRAM_MAX_ADDR_WIDTH(10),
                     .C_PICOBLAZE_INSTRUCTION_DATA_WIDTH(18),
                     .C_JTAG_CHAIN(2),
                     .C_ADDR_WIDTH_0(10))
                   u_loader( .picoblaze_reset(rdl),
                             .jtag_en(jtag_en),
                             .jtag_din(jtag_din),
                             .jtag_addr(jtag_addr),
                             .jtag_clk(jtag_clk),
                             .jtag_we(jtag_we),
                             .jtag_dout_0(jtag_dout),
                             .jtag_dout_1('b0),
                             .jtag_dout_2('b0),
                             .jtag_dout_3('b0),
                             .jtag_dout_4('b0),
                             .jtag_dout_5('b0),
                             .jtag_dout_6('b0),
                             .jtag_dout_7('b0));
  end else begin : NOJL
     assign jtag_en = 0;
     assign jtag_we = 0;
     assign jtag_clk = 0;
     assign jtag_din = {18{1'b0}};
     assign jtag_addr = {BRAM_ADR_WIDTH{1'b0}};
  end
endgenerate

// Debugging symbols. Note that they're
// only 48 characters long max.
// synthesis translate_off

// allocate a bunch of space for the text
   reg [8*48-1:0] dbg_instr;
   always @(*) begin
     case(address)
%for (row,v) in debug_data:
         ${row} : dbg_instr = "${v}";
%endfor
     endcase
   end
// synthesis translate_on


BRAM_TDP_MACRO #(
    .BRAM_SIZE("18Kb"),
    .DOA_REG(0),
    .DOB_REG(0),
    .INIT_A(18'h00000),
    .INIT_B(18'h00000),
    .READ_WIDTH_A(18),
    .WRITE_WIDTH_A(18),
    .READ_WIDTH_B(BRAM_PORT_WIDTH),
    .WRITE_WIDTH_B(BRAM_PORT_WIDTH),
    .SIM_COLLISION_CHECK("ALL"),
    .WRITE_MODE_A("WRITE_FIRST"),
    .WRITE_MODE_B("WRITE_FIRST"),
    // The following INIT_xx declarations specify the initial contents of the RAM
    // Address 0 to 255
%for (row, v) in group0_data:
    .INIT_${row}(256'h${v}),
%endfor

    // Address 256 to 511
%for (row, v) in group1_data:
    .INIT_${row}(256'h${v}),
%endfor

    // Address 512 to 767
%for (row, v) in group2_data:
    .INIT_${row}(256'h${v}),
%endfor

    // Address 768 to 1023
%for (row, v) in group3_data:
    .INIT_${row}(256'h${v}),
%endfor

    // The next set of INITP_xx are for the parity bits
    // Address 0 to 255
%for (row, v) in group0_parity:
    .INITP_${row}(256'h${v}),
%endfor

    // Address 256 to 511
%for (row, v) in group1_parity:
    .INITP_${row}(256'h${v}),
%endfor

    // Address 512 to 767
%for (row, v) in group2_parity:
    .INITP_${row}(256'h${v}),
%endfor

    // Address 768 to 1023
%for (row, v) in group3_parity:
    .INITP_${row}(256'h${v}),
%endfor

    // Output value upon SSR assertion
    .SRVAL_A(18'h000000),
    .SRVAL_B({BRAM_PORT_WIDTH{1'b0}})
) ramdp_1024_x_18(
    .DIA (18'h00000),
    .ENA (enable),
    .WEA ({BRAM_WE_WIDTH{1'b0}}),
    .RSTA(1'b0),
    .CLKA (clk),
    .ADDRA (address),
    // swizzle the parity bits into their proper place
    .DOA ({instruction[17],instruction[15:8],instruction[16],instruction[7:0]}),
    .DIB (bram_macro_din),
    .DOB (bram_macro_dout),
    .ENB (jtag_en),
    .WEB ({BRAM_WE_WIDTH{jtag_we}}),
    .RSTB(1'b0),
    .CLKB (jtag_clk),
    .ADDRB(jtag_addr)
);

endmodule
'''


tpl_dualport = '''\
`timescale 1 ps / 1ps

/* 
 * == pblaze-as ==
 * source : ${project}.s
 * create : ${ctime}
 * modify : ${mtime}
 */
/* 
 * == pblaze-ld ==
 * target : kcpsm3
 */

module ${project} (address, instruction, enable, clk, bram_adr_i, bram_dat_o, bram_dat_i, bram_en_i, bram_we_i, bram_rd_i);
parameter BRAM_PORT_WIDTH = 9;
localparam BRAM_ADR_WIDTH = (BRAM_PORT_WIDTH == 18) ? 10 : 11;
localparam BRAM_WE_WIDTH = (BRAM_PORT_WIDTH == 18) ? 2 : 1;
input [9:0] address;
input clk;
input enable;
output [17:0] instruction;
input [BRAM_ADR_WIDTH-1:0] bram_adr_i;
output [BRAM_PORT_WIDTH-1:0] bram_dat_o;
input [BRAM_PORT_WIDTH-1:0] bram_dat_i;
input bram_we_i;
input bram_en_i;
input bram_rd_i;

// Debugging symbols. Note that they're
// only 48 characters long max.
// synthesis translate_off

// allocate a bunch of space for the text
   reg [8*48-1:0] dbg_instr;
   always @(*) begin
     case(address)
%for (row,v) in debug_data:
         ${row} : dbg_instr = "${v}";
%endfor
     endcase
   end
// synthesis translate_on


BRAM_TDP_MACRO #(
    .BRAM_SIZE("18Kb"),
    .DOA_REG(0),
    .DOB_REG(0),
    .INIT_A(18'h00000),
    .INIT_B(18'h00000),
    .READ_WIDTH_A(18),
    .WRITE_WIDTH_A(18),
    .READ_WIDTH_B(BRAM_PORT_WIDTH),
    .WRITE_WIDTH_B(BRAM_PORT_WIDTH),
    .SIM_COLLISION_CHECK("ALL"),
    .WRITE_MODE_A("WRITE_FIRST"),
    .WRITE_MODE_B("WRITE_FIRST"),
    // The following INIT_xx declarations specify the initial contents of the RAM
    // Address 0 to 255
%for (row, v) in group0_data:
    .INIT_${row}(256'h${v}),
%endfor

    // Address 256 to 511
%for (row, v) in group1_data:
    .INIT_${row}(256'h${v}),
%endfor

    // Address 512 to 767
%for (row, v) in group2_data:
    .INIT_${row}(256'h${v}),
%endfor

    // Address 768 to 1023
%for (row, v) in group3_data:
    .INIT_${row}(256'h${v}),
%endfor

    // The next set of INITP_xx are for the parity bits
    // Address 0 to 255
%for (row, v) in group0_parity:
    .INITP_${row}(256'h${v}),
%endfor

    // Address 256 to 511
%for (row, v) in group1_parity:
    .INITP_${row}(256'h${v}),
%endfor

    // Address 512 to 767
%for (row, v) in group2_parity:
    .INITP_${row}(256'h${v}),
%endfor

    // Address 768 to 1023
%for (row, v) in group3_parity:
    .INITP_${row}(256'h${v}),
%endfor

    // Output value upon SSR assertion
    .SRVAL_A(18'h000000),
    .SRVAL_B({BRAM_PORT_WIDTH{1'b0}})
) ramdp_1024_x_18(
    .DIA (18'h00000),
    .ENA (enable),
    .WEA ({BRAM_WE_WIDTH{1'b0}}),
    .RSTA(1'b0),
    .CLKA (clk),
    .ADDRA (address),
    // swizzle the parity bits into their proper place
    .DOA ({instruction[17],instruction[15:8],instruction[16],instruction[7:0]}),
    .DIB (bram_dat_i),
    // it's your OWN damn job to deswizzle outside this module
    .DOB (bram_dat_o),
    .ENB (bram_en_i),
    .WEB ({BRAM_WE_WIDTH{bram_we_i}}),
    .RSTB(1'b0),
    .CLKB (clk),
    .ADDRB(bram_adr_i)
);

endmodule
'''


def file_get_contents(filename):
    fin = open(filename)
    text = fin.read()
    fin.close()
    return text

def file_put_contents(filename, s):
    fout = open(filename, 'w')
    fout.write(s)
    fout.close()

usage = '''\
usage: %s [option] [file]

  -h                print this help
  -o <file>         Place output into <file>, '-' is stdout.
''' % os.path.split(sys.argv[0])[1]

class PBLDException(BaseException):
    def __init__(self, msg):
        self.msg = msg

def parse_commandline():
    s_config = 'ho:'
    l_config = ['help','dualport']

    try:
        opts, args = getopt.getopt(sys.argv[1:], s_config, l_config)
        #convert to map
        map_config = {}
        for (k, v) in opts:
            map_config[k] = v

        if ('-h' in map_config) or ('--help' in map_config) or len(args) == 0:
            print usage
            sys.exit(0)

        if '-o' not in map_config:
            name_without_path = os.path.split(args[0])[1]
            name_without_ext = os.path.splitext(name_without_path)[0]
            map_config['-o'] = name_without_ext + '.v'
        else:
            name_without_path = os.path.split(map_config['-o'])[1]
            name_without_ext = os.path.splitext(name_without_path)[0]

        map_config['--project'] = name_without_ext

        if len(args) != 1:
            raise PBLDException('Just support one object file!')

        map_config['-i'] = args[0]

    except PBLDException as e:
        print e.msg
        print
        print usage
        sys.exit(-1)

    return map_config

def load_object(map_config):
    #load object
    s = file_get_contents(map_config['-i'])
    map_object = json.loads(s)

    #fill zero to fix 1024
    n_padding = 1024 - len(map_object['object'])
    if n_padding > 0:
        print 'append %d zero to rom' % n_padding
        for i in range(n_padding):
            map_object['object'].append(0)

    return map_object

def convert_to_blockram(map_object):
    #split to data and parity
    row_data    = 0
    row_parity  = 0
    lst_data    = []
    lst_parity  = []

    n = len(map_object['object'])
    lst_d_cols = []
    lst_p_cols = []
    for i in range(n):
        #bit17_16 save to p
        #bit15_00 save to d
        v = map_object['object'][i]
        p = (v & 0x30000) >> 16
        d = v & 0xFFFF
        lst_d_cols.append(d)
        lst_p_cols.append(p)

        #convert to 256'h format
        if (i % 16) == 15:
            #prepare
            lst_d_cols.reverse()
            row = '%02X' % row_data
            row_data += 1
            #digit to string
            s = ''.join(['%04X' % tmp for tmp in lst_d_cols])
            #append
            lst_data.append((row, s))
            lst_d_cols = []

        if (i % 128) == 127:
            #convert 2bits to 4bits mode
            lst_tmp_p = []
            for j in range(64):
                tmp = lst_p_cols[2*j + 0] | (lst_p_cols[2*j + 1] << 2);
                lst_tmp_p.append(tmp)
            #preapre
            lst_tmp_p.reverse()
            row = '%02X' % row_parity
            row_parity += 1
            #digit to string
            s = ''.join(['%01X' % tmp for tmp in lst_tmp_p])
            #append
            lst_parity.append((row, s))
            lst_p_cols = []

    return (lst_data, lst_parity)

def render(map_config, map_object, lst_data, lst_parity,debug_data):
    n = len(lst_data)
    step = n / 4
    group0_data = lst_data[0*step:1*step]
    group1_data = lst_data[1*step:2*step]
    group2_data = lst_data[2*step:3*step]
    group3_data = lst_data[3*step:4*step]

    n = len(lst_parity)
    step = n / 4
    group0_parity = lst_parity[0*step:1*step]
    group1_parity = lst_parity[1*step:2*step]
    group2_parity = lst_parity[2*step:3*step]
    group3_parity = lst_parity[3*step:4*step]

    tmpl = None
    if '--dualport' not in map_config:
        tmpl = Template(tpl_oneport)
    else:
        tmpl = Template(tpl_dualport)
        
    text = tmpl.render(
            project=map_config['--project'],
            ctime=map_object['ctime'],
            mtime=map_object['mtime'],
            debug_data=debug_data,
            group0_data=group0_data,
            group1_data=group1_data,
            group2_data=group2_data,
            group3_data=group3_data,
            group0_parity=group0_parity,
            group1_parity=group1_parity,
            group2_parity=group2_parity,
            group3_parity=group3_parity)
    return text

if __name__ == '__main__':
    map_config = parse_commandline()
    map_object = load_object(map_config)
    
    # let's try to construct debugging info!
    labels = map_object['labels']
    # sort all labels by their address
    fn = sorted(labels.items(), key=lambda x: x[1])
    fn.reverse()
    # get the first label
    nextline = fn.pop()
    i=0
    current_function = None
    debug_data = []
    while i < 1024:
        label = ""
        # are we out of labels?
        if nextline == None:
            label = "%s+0x%3.3x" % (current_function[0], i-current_function[1])
        # have we reached the target label?        
        elif nextline[1] == i:
            label = nextline[0]            
            current_function = nextline
            while nextline[1] == i:
                # if no more, break out
                if len(fn) == 0:
                    nextline = None
                    break
                tmp = fn.pop()
                # autolabel?                
                if re.match(r'L_[a-z0-9]*_[0-9]*', tmp[0]):
                    # if no more, break out
                    if len(fn) == 0:
                        nextline = None
                        break
                    # otherwise skip
                elif re.match(r'JOIN_[0-9]*', tmp[0]):
                    if len(fn) == 0:
                        nextline = None
                        break
                    # otherwise skip
                elif re.match(r'_end_.*', tmp[0]):
                    if len(fn) == 0:
                        nextline = None
                        break
                    # otherwise skip
                else:
                    nextline = tmp                    
        else:
            # nope, we're incrementing
            label = "%s+0x%3.3x" % (current_function[0], i-current_function[1])

        label = label.ljust(48)
        label = label[0:47]            
        debug_data.append((i, label))
        i = i + 1
                        
    (lst_data, lst_parity) = convert_to_blockram(map_object)
    text = render(map_config, map_object, lst_data, lst_parity, debug_data)

    #insert pblaze-cc information
    lst_text = []
    lst_text.append('/*')
    lst_text.append(' * == pblaze-cc ==')
    if 'pblaze-cc' in map_object:
        for (k, v) in map_object['pblaze-cc']:
            lst_text.append(' * %s : %s' % (k, v))
    lst_text.append(' */')
    text = '\n'.join(lst_text) + '\n' + text

    if map_config['-o'] == '-':
        print text
    else:
        file_put_contents(map_config['-o'], text)
        print 'wrote %d bytes to "%s"' % \
            (len(text), map_config['-o'])

    print

