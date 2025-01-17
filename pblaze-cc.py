#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#  
#  Copyright 2013 buaa.byl@gmail.com
#  Copyright 2020 dbarawn@gmail.com
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
# 2017.01.11    add exe path to include search directory.
# 2020.01.04    add a lot of features (multi-register, Z/C, single-while)
#
# this is fake c compiler.
# I write this script for easy write assembly code.
# So this "compiler" is a translator, not a really compiler.
#

import os
import sys
import re
import time
import traceback
import hashlib
import types
import subprocess
import getopt
from io import StringIO

BASEADDR_INTC_CLEAR = 0xF0

#gnu style use 2 spaces as tab
NR_SPACES_OF_TAB = 2

#index of each line
IDX_LEVEL   = 0
IDX_LINENO  = 1
IDX_TYPE    = 2
IDX_CODE    = 3

labels = []

vivado_boot_fix = False
super_verbose = False

class MetaInfo(object):
    def __init__(self):
        self.level = 0
        self.lineno = 0
        self.lines = []
        self.filename = ''

class ParseException(BaseException):
    def __init__(self, msg):
        self.msg = msg

def file_get_contents(fn):
    f = open(fn, "r")
    d = f.read()
    f.close()
    return d

def file_put_contents(fn, d):
    f = open(fn, "w")
    f.write(d)
    f.close()

def resolve_lineno(text):
    lst_line = []
    lines = text.split('\n')
    filename = ''
    lineno   = 1

    for line in lines:
        res = re.match(r'#line (\d+) "(.*)"', line)
        if res:
            filename = res.groups()[1]
            lineno = int(res.groups()[0])
            continue

        if not re.match(r'^[ \t]*$', line):
            lst_line.append('#line %d "%s"' % (lineno, filename))

        lst_line.append(line)

        lineno += 1

    return lst_line

def popen(args, stdin=None):
    p = subprocess.Popen(args,
            stdin = subprocess.PIPE,
            stdout = subprocess.PIPE,
            stderr = subprocess.PIPE,
            universal_newlines = True)

    stdout_text, stderr_text = p.communicate(stdin)
    p.wait()

    return (p.returncode, stdout_text, stderr_text)

def _parse_param(param):
    param = re.sub(r'[ ]+', '', param)
    if super_verbose == True:
        print("parsing")
        print(param)
    if len(param) == 0:
        return param
    elif re.match(r'[Z|C]', param):
        return param
    elif re.match(r'^s[0-9A-F]$', param):
        return param
    elif re.match(r'^[&]s[0-9A-F]$', param):
        return param[1:]
    elif re.match(r'^(s[0-9A-F].)*s[0-9A-F]$',param):
        if super_verbose == True:
            print("match multi-register")
        return param
    elif re.match(r'^[&](s[0-9A-F].)*s[0-9A-F]$',param):
        if super_verbose == True:
            print("match multi-register")
        return param[1:]
    else:
        try:
            res = {'val':0}
            text = 'val = %s' % param
            exec(text, {}, res)
            return res['val']
        except SyntaxError as e:
            traceback.print_exc()
            raise ParseException("Unknown format")

def _parse_param_list(params):
    params = re.split(r'[,]', params)

    #param must be register or digit or assignment
    lst_param = []
    for param in params:
        lst_param.append(_parse_param(param))

    return lst_param

def prepare(info, line):
    info.lineno += 1

    info.level = 0
    for c in line:
        if c != ' ':
            break
        info.level += 1

    info.level /= NR_SPACES_OF_TAB

    line = re.sub(r'^[ \t]+', '', line)

    return line

def parse_macro(info, line):
    line = re.sub(r'[; ]+$', '', line)

    res = re.match(r'#include "(.*)"', line)
    if res:
        return True
    
    res = re.match(r'#line (\d+) "(.*)"', line)
    if res:
        info.filename = res.groups()[1]
        info.lineno = int(res.groups()[0]) - 1
        return True

    return False

def parse_block(info, line):
    line = re.sub(r'[; ]+$', '', line)

    if line == '{':
        info.lines.append([info.level, info.lineno, 'block', line])
        #info.level += 1
        return True

    if line == '}':
        #info.level -= 1
        info.lines.append([info.level, info.lineno, 'block', line])
        return True

    return False

def parse_return(info, line):
    line = re.sub(r'[; ]+$', '', line)

    if line == 'return':
        info.lines.append([info.level, info.lineno, 'return', []])
        return True

    res = re.match(r'return (.*)', line)
    if res:
        param = _parse_param(res.groups()[0])
        if int(param) != 0:
            param = 'enable'
        else:
            param = 'disable'

        info.lines.append([info.level, info.lineno, 'return', param])
        return True

    return False 

def parse_do(info, line):
    line = re.sub(r'[; ]+$', '', line)

    if line == 'do':
        info.lines.append([info.level, info.lineno, 'do', []])
        return True

    return False

def parse_break(info, line):
    line = re.sub(r'[; ]+$', '', line)
    
    if line in ['break', 'continue']:
        info.lines.append([info.level, info.lineno, line, []])
        return True

    return False

def parse_condition(info, line):
    end_while = False
    #check if end with ';'
    if re.match(r'.+[;]+[ \t]*$', line):
        end_while = True 

    line = re.sub(r'[; ]+$', '', line)

    #strip more space
    line = re.sub(r'[ \t]+',' ', line)
    line = re.sub(r'\([ ]+', '(', line)
    line = re.sub(r'[ ]+\)', ')', line)
    #print repr(line)

    inverted = False
    
    if line == 'else':
        info.lines.append([info.level, info.lineno, 'else', []])
        return True

    #let's try recognizing if (!( blah ))    
    res = re.match(r'(if|else if|while)\s*\(!(\(.*\))\)', line)
    if res:
        print("recognized an inverted comparison, try to flop its logic later")
        inverted = True
        newline = "%s %s" % ( res.groups()[0] , res.groups()[1])        
        print("converting '%s' to inverted '%s'" % ( line , newline ))
        line = newline

    #fmt: if (var--)
    res = re.match(r'(if|else if|while)\s*\((.+)--\s*\)', line)
    if res:
        cond = res.groups()[0]
        param0 = res.groups()[1]
        compare = '--'
        # this indicates a C test
        param1 = '-1'
        if inverted:
            # hide the inversion in the compare parameter, we'll
            # know what to do later.
            param1 = '-2'

        if cond == 'while' and end_while:
            if super_verbose == True:
                print("while and end_while")
            info.lines.append([info.level, info.lineno, 'dowhile',
                [compare, _parse_param(param0), _parse_param(param1)]])
            return True        

        info.lines.append([info.level, info.lineno, cond,
            [compare, _parse_param(param0), _parse_param(param1)]])
        return True

            
    #fmt: if (--var)
    #we actually need a separate case for (s--), deal with that
    #later. s-- uses C as a test, rather than Z. We might
    #embed that in param1: we could use -1 and -2 as the [truth, inverted]
    #case there.
    #There will never be an if (a++) operator, we can't do that
    #(can't test for 1), but there may be a (++a) operator.
    res = re.match(r'(if|else if|while)\s*\(\s*--(.+)\)', line)
    if res:
        cond = res.groups()[0]
        param0 = res.groups()[1]
        compare = '--'
        param1 = '0'
        
        if inverted:
            # hide the inversion in the compare parameter
            param1 = '1'
        
        if cond == 'while' and end_while:
            if super_verbose == True:
                print("while and end_while")
            info.lines.append([info.level, info.lineno, 'dowhile',
                [compare, _parse_param(param0), _parse_param(param1)]])
            return True        

        info.lines.append([info.level, info.lineno, cond,
            [compare, _parse_param(param0), _parse_param(param1)]])
        return True
    
    #fmt: if (!var)
    res = re.match(r'(if|else if|while)\s*\(!\s*(.+)\)', line)
    if res:
        cond    = res.groups()[0]
        param0  = res.groups()[1]
        # we can do inversions here automatically
        # you're a bastard for doing if (!(!a)) but whatever, some macros
        # might generate this
        if inverted:
            compare = '!='
        else:
            compare = '=='
        param1 = '0'
        if cond == 'while' and end_while:
            info.lines.append([info.level, info.lineno, 'dowhile',
                [compare, _parse_param(param0), _parse_param(param1)]])
            return True

        info.lines.append([info.level, info.lineno, cond,
            [compare, _parse_param(param0), _parse_param(param1)]])
        return True
    
    #fmt: if (a & b) or if (a ^ b)
    # Note that if (a | b) is NOT representable in PicoBlaze.
    # you have to do a |= b, if (a).
    #
    # But if (a & b) is representable by test NZ,
    # and if (a ^ b) is the complement of that (test Z).
    res = re.match(r'(if|else if|while)\s*\((.+) (&|\^) (.+)\)', line)
    if res:
        cond    = res.groups()[0]
        param0  = res.groups()[1]
        compare = res.groups()[2]
        param1  = res.groups()[3]

        if inverted:
            if compare == '&':
                compare = '^'
            elif compare == '^':
                compare = '&'
            print("inverted '%s' became '%s %s %s %s'" % (line, cond, param0, compare, param1))
                        
        if cond == 'while' and end_while:
            info.lines.append([info.level, info.lineno, 'dowhile',
                [compare, _parse_param(param0), _parse_param(param1)]])
            return True
        
        info.lines.append([info.level, info.lineno, cond,
            [compare, _parse_param(param0), _parse_param(param1)]])
        return True

    #fmt: if (a < b)
    res = re.match(r'(if|else if|while)\s*\((.+) (>|<|==|!=|>=|<=) (.+)\)', line)
    if res:
        cond    = res.groups()[0]
        param0  = res.groups()[1]
        compare = res.groups()[2]
        param1  = res.groups()[3]

        # we can invert these here.
        if inverted:
            if compare == "==":
                compare = "!="
            elif compare == "!=":
                compare = "=="
            elif compare == "<":
                compare = ">="
            elif compare == ">":
                compare = "<="
            elif compare == "<=":
                compare = ">"
            elif compare == ">=":
                compare = "<"
            print("'%s' became '%s %s %s %s'" % (line, cond, param0, compare, param1))
        
        if cond == 'while' and end_while:
            info.lines.append([info.level, info.lineno, 'dowhile',
                [compare, _parse_param(param0), _parse_param(param1)]])
            return True

        info.lines.append([info.level, info.lineno, cond,
            [compare, _parse_param(param0), _parse_param(param1)]])
        return True

    #fmt: if (1)
    res = re.match(r'(if|else if|while)\s*\((s[0-9a-fA-F]|\d+|[ZC])\)', line)
    if res:
        cond    = res.groups()[0]
        param0  = res.groups()[1]
        # inversion here is easy. This happens if you do
        # if (!(s0)) which I'm fine with
        if inverted:
            compare = '=='
        else:
            compare = '!='
        param1  = '0'

        if cond == 'while' and end_while:
            info.lines.append([info.level, info.lineno, 'dowhile',
                [compare, _parse_param(param0), _parse_param(param1)]])
            return True

        info.lines.append([info.level, info.lineno, cond,
            [compare, _parse_param(param0), _parse_param(param1)]])
        return True

    return False 

def parse_assign(info, line):
    line = re.sub(r'[; ]+$', '', line)

    #fmt: a += b
    res = re.match(r'(.+) (=|\+=|-=|<<=|>>=|&=|\|=|\^=) (.+)', line)
    if res:
        param0  = res.groups()[0]
        assign  = res.groups()[1]
        param1  = res.groups()[2]
        info.lines.append([info.level, info.lineno, 'assign',
            [assign, _parse_param(param0), _parse_param(param1)]])
        return True

    #fmt: a++
    res = re.match(r'(.+)\s*(\+\+|--)', line)
    if res:
        param0  = res.groups()[0]
        assign  = res.groups()[1]
        assign  = {'++':'+=', '--':'-='}[assign]

        info.lines.append([info.level, info.lineno, 'assign',
            [assign, _parse_param(param0), 1]])
        return True

    return False 

def parse_label(info, line):
    if super_verbose == True:
        print("Parsing %s" % line)
    res = re.match(r'(\w+)\s*:', line)
    if res:
        if super_verbose == True:
            print("found label")
        ret = None
        name = res.groups()[0]
        params = None
        attributes = None
        labels.append(name)
        info.lines.append([info.level, info.lineno, 'label',
                           [name, ret, params, attributes]])
        return True

def parse_goto(info, line):
    res = re.match(r'goto \s*(\w+)\s*;', line)
    if res:
        if super_verbose == True:
            print("found goto")
        ret = None
        name = res.groups()[0]
        params = None
        attributes = None
        info.lines.append([info.level, info.lineno, 'goto',
                           [name, ret, params, attributes]])
        return True
    
def parse_funcdecl(info, line):
    if super_verbose == True:
        print("Parsing %s" % line)
    #ignore normal function declare
    if re.match(r'(\w+) (\w+)\s*\(([^\(\)]*)\);$', line):
        if super_verbose == True:
            print("not a function")
        return True

    #parse __attribute__ ((...))
    res = re.match(r'(\w+) (\w+)\s*\((.*)\) (.*);$', line)
    if info.level == 0 and res:
        if super_verbose == True:
            print("found function at %s" % line)
        ret = res.groups()[0]
        name = res.groups()[1]
        params = res.groups()[2]
        attributes = res.groups()[3]
        if super_verbose == True:
            print("ret %s" % ret)
            print("name %s" % name)
            print("params %s" % params)
            print("attributes %s" % attributes)
        info.lines.append([info.level, info.lineno, 'funcdecl', 
            [name, ret, params, attributes]])
        return True

    return False 

def parse_funcdef(info, line):
    if super_verbose == True:
        print("parsing %s" % line)
    line = re.sub(r'[; ]+$', '', line)
    if super_verbose == True:
        print("subbed to %s" % line)
    res = re.match(r'(\w+) (\w+)\s*\((.*)\)$', line)
    if info.level == 0 and res:
        if super_verbose == True:
            print("function")
        ret = res.groups()[0]
        name = res.groups()[1]
        params = res.groups()[2]
        info.lines.append([info.level, info.lineno, 'funcdef', 
            [name, ret, params]])
        info.lines.append([info.level, info.lineno, 'file', 
            [info.filename]])
        return True

    return False 

def parse_funccall(info, line):
    line = re.sub(r'[; ]+$', '', line)

    res = re.match(r'(\w+)\((.*)\)$', line)
    if res:
        fun = res.groups()[0]
        params = res.groups()[1]

        if len(params) == 0:
            info.lines.append([info.level, info.lineno, 'funccall', [fun]])
            return True

        if fun in ['input', 'output', 'outputk', 'store', 'fetch', 'test']:
            info.lines.append([info.level, info.lineno, 'funccall',
                [fun, _parse_param_list(params)]])
        else:
            info.lines.append([info.level, info.lineno, 'funccall',
                [fun, [params]]])
        return True

    return False 

def parse(text):
    lines = text.split('\n')
    info = MetaInfo()

    #build parser list
    lst_parser = [
            parse_macro,
            parse_block,
            parse_return,
            parse_do,
            parse_break,
            parse_condition,
            parse_assign,
            parse_funcdecl,
            parse_funcdef,
            parse_funccall,
            parse_label,
            parse_goto
    ]

    #parse codes
    for line in lines:
        line = prepare(info, line)

        if re.match(r'^[ \t;]+$', line) or len(line) == 0:
            continue

        line = re.sub(r'[\t ]+', ' ', line)

        #try all know parser
        unknown = True
        for parser in lst_parser:
            #print(parser.__name__)
            if parser(info, line):
                unknown = False
                break

        if unknown:
            msg = 'Unknown format "%d:%s"' % (info.lineno, line)
            raise ParseException(msg)

    if super_verbose == True:
        print("info line dump")
        for line in info.lines:
            print(line)
    # We need to reprocess the lines to look to see if we misidentified
    # a while() statement as a do/while loop.
    # Because of the astyle processing, this actually only happens
    # if there's an empty while statement, like
    # while (s0--);
    # We identify this by looking for a 'dowhile' that is NOT
    # immediately preceded by a closing brace.
    # Again, thanks to astyle, this is a GUARANTEE that
    # we've screwed up the do/while identification.
    idx = 0
    while idx < len(info.lines):
        line = info.lines[idx]
        if line[IDX_TYPE] == 'dowhile':
            singlewhile = False
            if idx == 0:
                # if idx is zero, we've definitely effed it up
                # don't know how that would happen, buuuut
                print("Single-line while (line 0)")
                print("Line is:", line[IDX_CODE])
                singlewhile = True
            else:
                test_lineno = line[IDX_LINENO]
                previous_code = info.lines[idx-1][IDX_CODE]
                previous_type = info.lines[idx-1][IDX_TYPE]
                previous_lineno = info.lines[idx-1][IDX_LINENO]
                if previous_type != 'block':
                    print("Single-line while at %d (previous type is %s)" % (test_lineno, previous_type))
                    print("Line is:", line[IDX_CODE])
                    singlewhile = True
                elif previous_code != '}':
                    print("Single-line while at %d (previous block is %s)" % (test_lineno, previous_code))
                    print("Line is:", line[IDX_CODE])
                    singlewhile = True
                elif (test_lineno - previous_lineno != 1):
                    print("Single-line while at %d (previous closing brace at %d)" % (test_lineno, previous_lineno))
                    print("Line is:", line[IDX_CODE])
                    singlewhile = True
            if singlewhile:
                info.lines[idx][IDX_TYPE] = 'singlewhile'
        idx = idx + 1
    return info

def dump_parse(lines, no_title=False, f=sys.stdout):
    show_title = not no_title

    if show_title:
        f.write('/* %5s %6s %10s */' % ('level', 'lineno', 'type'))
        f.write('\n')
        f.write('/*%s*/' % ('*'*80))
        f.write('\n')

    for level, lineno, t, code in lines:
        f.write('/* %5d %6d %10s */ %s%s' % \
                (level, lineno, t, '    ' * level, code))
        f.write('\n')
    f.write('\n')

def convert_list_to_block(info):
    #return value format:
    #   (
    #       {
    #           function_name : [
    #               (label, [
    #                       (level, lineno, type, code),
    #                       ......
    #               ]
    #               ),
    #               ......
    #           ],
    #           ......
    #       },
    #       {
    #           function_name : attribute,
    #           ......
    #       }
    #   )
    body = []
    map_function = {}
    map_attribute = {}

    #group by function
    for line in info.lines:
        level, lineno, t, code = line
        if t == 'funcdecl':
            name = code[0]
            attributes = code[3]
            # I have NO IDEA what this was supposed to do.
            # 
            res = re.match('__attribute__[ \t]*\(\((.+)\W*\((.+)\)\)\)', attributes)
            res2 = re.match('__attribute__\s*\(\(\s*(\w+)\s*\)\)', attributes)
            if res:
                print("complex attribute match")
                clear_attrs = []
                attrs = res.groups()
                for attr in attrs:
                    attr = re.sub('^[ ]+', '', attr)
                    attr = re.sub('[ ]+$', '', attr)
                    if re.match(r'"(.+)"', attr):
                        to_append = re.match(r'"(.+)"', attr).groups()[0]
                        print("appending", to_append)
                        clear_attrs.append(to_append)
                    else:
                        clear_attrs.append(attr)

                map_attribute[name] = clear_attrs
            elif res2:
                attr = res2.groups()[0]
                if attr == "noreturn":
                    print("Function '%s' with attribute noreturn, adding to label list" % name)
                    labels.append(name)
            else:
                msg = 'Unknown attribute format "%s"' % attributes
                raise ParseException(msg)
        elif t == 'funcdef':
            name = code[0]
            body = [line]
            map_function[name] = body
            if super_verbose == True:
                print("new function", name)
        elif t == 'file':
            body.insert(0, line)
        elif t == 'block':
            continue
        else:
            if super_verbose == True:
                print("adding", line, "to function")
            body.append(line)

    ##debug
    #for name, body in map_function.iteritems():
    #    print 'DEBUG:', name, 'has', len(body), 'lines'
    #print

    #group by level
    label_prefix = ''
    label_id = 0

    for name in map_function:
        curr_level = 0
        body = map_function[name]

        #convert body to list of block
        lst_block = []

        begin = 0
        i = 0
        for i in range(len(body)):
            line = body[i]
            level, lineno, t, code = line

            if t == 'file':
                fpath = code[0]
                label_prefix = 'L_%s_' % hashlib.md5(fpath.encode()).hexdigest()
                i += 1

            elif level != curr_level or t in ['do', 'singlewhile', 'dowhile', 'while', 'if',
                    'else if', 'else', 'break', 'continue']:
                if i - begin > 0 and len(body[begin:i]) > 0:
                    #generate label
                    label = label_prefix + str(label_id)
                    label_id += 1
                    
                    #save previous lines
                    lst_block.append((label, body[begin:i]))

                #preapre next
                curr_level = level
                begin = i
                i += 1

                if t in ['do', 'dowhile', 'while', 'if']:
                    if i - begin > 0 and len(body[begin:i]) > 0:
                        #generate label
                        label = label_prefix + str(label_id)
                        label_id += 1

                        #save current line
                        lst_block.append((label, body[begin:i]))

                    begin = i
                    i += 1
            else:
                i += 1

        if i - begin > 0 and len(body[begin:i]) > 0:
            label = label_prefix + str(label_id)
            label_id += 1

            lst_block.append((label, body[begin:i]))

        #replace body to list of block
        map_function[name] = lst_block

    ##debug
    #for name, body in map_function.iteritems():
    #    l = 0
    #    for label, block in body:
    #        l += len(block)
    #    print 'DEBUG:', name, 'has', l, 'lines'
    #print

    return (map_function, map_attribute)

def dump_blocks(map_function, f=sys.stdout):
    #debug
    for name in map_function:
        lst_block = map_function[name]
        f.write(name)
        f.write('\n')
        no_title = False
        for block in lst_block:
            f.write(' %s:' % block[0])
            f.write('\n')
            dump_parse(block[1], no_title, f)
            no_title = True

def convert_condition_to_ifgoto(map_function):
    #because 'if'/'do'/'while' is in single line block,
    #so easy to modify it.

    for name in map_function:
        lst_block = map_function[name]

        stack_label = []
        prev_level = 0

        map_pair = {}

        stack_cond_level = []
        stack_cond_label = []

        #find level-pair, such like 'do' and 'while', '{' and '}'
        #and convert 'do-while'/'while' to 'if, cond, label(true), label(false)'
        #and convert 'if' to 'if, cond, label(true), label(false)'
        for idx_block in range(len(lst_block)):
            #get current info
            label, block = lst_block[idx_block]
            level = block[0][0]

            #get next info
            idx_next_block = idx_block + 1
            if idx_next_block < len(lst_block):
                label_next, block_next = lst_block[idx_next_block]
                level_next = block_next[0][0]
            else:
                label_next = None
                block_next = None
                level_next = -1

            #check
            if level > 0 and label_next:
                if level < level_next:#next block is lowest
                    stack_label.append((level, idx_block, label))
                    if block[0][2] in ['do', 'while']:
                        stack_cond_level.append(level_next)
                        stack_cond_label.append(label)
                elif level > level_next:#next block is higest
                    while True:
                        (old_level, old_idx, old_label) = stack_label.pop(-1)

                        child_level = level

                        #check while
                        old_block = lst_block[old_idx][1]
                        level, lineno, t1, code = old_block[0]
                        if t1 == 'do':
                            child_level = stack_cond_level.pop(-1)
                            stack_cond_label.pop(-1)
                        elif t1 in ['while', 'if']:
                            if t1 == 'while':
                                child_level = stack_cond_level.pop(-1)
                                stack_cond_label.pop(-1)

                            code.append('(NEXT)')

                            #find next same level code
                            label_bb = ''
                            if len(stack_cond_label) > 0:
                                level_insde_loop = stack_cond_level[-1]
                                for tmp_label, tmp_block in lst_block[idx_next_block:]:
                                    tmp_level = tmp_block[0][0]
                                    if tmp_level == level:
                                        #match same level first
                                        label_bb = tmp_label
                                        break
                                    elif tmp_level == level_insde_loop:
                                        #match previous loop body
                                        label_bb = tmp_label
                                        break

                            if label_bb != '':
                                code.append(label_bb)
                            elif len(stack_cond_label) > 0:
                                code.append(stack_cond_label[-1])
                            else:
                                code.append(label_next)

                            old_block[0][2] = 'if'
                        else:
                            msg = 'Unknown condition "%s"' % str(t1)
                            raise ParseException(msg)

                        level, lineno, t, code = block[0]
                        if t1 == 'while':
                            block.append([child_level, lineno, 'goto', [old_label]])

                        #check do-while
                        level, lineno, t, code = block_next[0]
                        if t == 'dowhile':
                            map_pair[label_next] = old_label
                            block_next[0][2] = 'if'
                            code.append(old_label)
                            code.append('(NEXT)')
                        else:
                            map_pair[old_label] = label_next

                        if old_level == level_next:
                            break
                        elif old_level < level_next:
                            raise ParseException('Not pair levels!')

            elif level > 1 and label_next == None:
                (old_level, old_idx, old_label) = stack_label.pop(-1)

                #check while
                old_block = lst_block[old_idx][1]
                level, lineno, t, code = old_block[0]
                if t in ['if', 'while']:
                    code.append('(NEXT)')
                    code.append('(END)')
                    old_block[0][2] = 'if'

                level, lineno, t, code = block[0]
                block.append([level, lineno, 'goto', [old_label]])

                map_pair[old_label] = '(END)'

            pass#end of for idx_block in range(len(lst_block)):

def find_next_label(lst_block, level):
    label_bb = '(END)'
    for tmp_label, tmp_block in lst_block:
        tmp_level = tmp_block[0][0]
        if tmp_level <= level:
            label_bb = tmp_label
            break
    return label_bb

def find_prev_label(lst_block, level):
    label_bb = '(HEAD)'
    for tmp_label, tmp_block in reversed(lst_block):
        tmp_level = tmp_block[0][0]
        if tmp_level <= level:
            label_bb = tmp_label
            break
    return label_bb

def find_next_endif_label(lst_block, level):
    label_bb = '(END)'
    for tmp_label, tmp_block in lst_block:
        tmp_level = tmp_block[0][IDX_LEVEL]
        if tmp_level <= level and tmp_block[0][IDX_TYPE] == 'endif':
            label_bb = tmp_label
            break
    return label_bb

def find_next_endwhile_label(lst_block):
    label_bb = '(END)'
    for tmp_label, tmp_block in lst_block:
        if tmp_block[0][IDX_TYPE] in ['endwhile', 'dowhile']:
            label_bb = tmp_label
            break
    return label_bb

def find_prev_loop_label(lst_block):
    label_bb = '(END)'
    for tmp_label, tmp_block in reversed(lst_block):
        if tmp_block[0][IDX_TYPE] in ['while', 'do']:
            label_bb = tmp_label
            break
    return label_bb

def find_blockidx_of_label(lst_block, label):
    for i in range(len(lst_block)):
        if lst_block[i][0] == label:
            return i
        i += 1

    return None

def convert_condition_to_ifgoto2(map_function):
    label_prefix = 'JOIN_'
    label_id = 0

    #append endfunc to every block
    for name in map_function:
        lst_block = map_function[name]
        end_label = label_prefix + str(label_id)
        label_id += 1

        first_line = lst_block[0][1][0]

        end_block = [first_line[IDX_LEVEL], first_line[IDX_LINENO],
                'endfunc', []]

        lst_block.append((end_label, [end_block]))

    #insert join or endif block to control-graphic
    #
    #   if          ->  if
    #       ...     ->      ...
    #               ->  ifjoin
    #   else        ->  else
    #       ...     ->      ...
    #               ->  endif
    #
    for name in map_function:
        if super_verbose == True:
            print("processing function", name)
        lst_block = map_function[name]

        map_forward = {}
        map_backward = {}

        if super_verbose == True:
            print("lst_block dump")
            for block in lst_block:
                print(block)

        idx_block = 0
        while idx_block < len(lst_block):
            label, block = lst_block[idx_block]
            first_line = block[0]
            level = first_line[IDX_LEVEL]

            if super_verbose == True:
                print(idx_block, "first_line ", first_line, "level", level)

            # single whiles are special, they have no body of code to jump to.
            # so you don't want to look for the next label (which is the label after the compare)
            # you instead want to look for the label of the compare
            # This is why we identify them specially.
            if first_line[IDX_TYPE] in ['singlewhile']:
                # loops back to itself
                if super_verbose == True:
                    print("singlewhile labelling")
                label_t_next = lst_block[idx_block][0]
                label_f_next = find_next_label(lst_block[idx_block+1:], level)
                first_line[IDX_CODE].append(label_t_next)
                first_line[IDX_CODE].append(label_f_next)                
            elif first_line[IDX_TYPE] in ['if', 'else', 'else if', 'while']:
                if idx_block+1 < len(lst_block):
                    label_t_next = lst_block[idx_block+1][0]
                    if super_verbose == True:
                        print("label_t_next ", label_t_next)                    
                else:
                    label_t_next = '(END)'
                label_f_next = find_next_label(lst_block[idx_block+1:], level)

                #append true and false branch label
                first_line[IDX_CODE].append(label_t_next)
                first_line[IDX_CODE].append(label_f_next)

                #append node
                i_block = find_blockidx_of_label(lst_block, label_f_next)
                if i_block:
                    join_label = label_prefix + str(label_id)
                    label_id += 1

                    i_type = 'ifjoin'
                    if first_line[IDX_TYPE] in ['if', 'else if', 'else']:
                        if lst_block[i_block][1][0][IDX_TYPE] not in ['else', 'else if']:
                            i_type = 'endif'
                    elif first_line[IDX_TYPE] == 'while':
                        i_type = 'endwhile'

                    join_block = [first_line[IDX_LEVEL], first_line[IDX_LINENO],
                            i_type, [label]]

                    lst_block.insert(i_block, (join_label, [join_block]))

            elif first_line[IDX_TYPE] == 'dowhile':
                label_t_next = find_prev_label(lst_block[:idx_block], level)
                if idx_block+1 < len(lst_block):
                    label_f_next = lst_block[idx_block+1][0]
                else:
                    label_f_next = '(END)'

                if super_verbose == True:
                    print(label_t_next)
                    print(label_f_next)
                first_line[IDX_CODE].append(label_t_next)
                first_line[IDX_CODE].append(label_f_next)

            idx_block += 1

    #resolved label for else and else-if which will jump to endif
    for name in map_function:
        lst_block = map_function[name]
        if super_verbose == True:
            print("processing ", name)

        for idx_block in range(len(lst_block)):
            label, block = lst_block[idx_block]
            first_line = block[0]
            level = first_line[IDX_LEVEL]
            if name == "init":
                if super_verbose == True:
                    print("first_line ", first_line)
            if first_line[IDX_TYPE] == 'ifjoin':
                label_bb = find_next_endif_label(lst_block[idx_block+1:], level)
                first_line[IDX_CODE].append(label_bb)

            elif first_line[IDX_TYPE] == 'continue':
                #find while or do
                label_bb = find_prev_loop_label(lst_block[:idx_block])
                first_line[IDX_CODE].append(label_bb)

            elif first_line[IDX_TYPE] == 'break':
                #find while or do
                label_bb = find_prev_loop_label(lst_block[:idx_block])
                #extract false branch label of while or do
                block_loop_idx = find_blockidx_of_label(lst_block, label_bb)
                loop_block = lst_block[block_loop_idx][1][0]
                label_f_target = loop_block[IDX_CODE][-1]

                first_line[IDX_CODE].append(label_f_target)

    ##debug
    #print
    #for name in map_function:
    #    lst_block = map_function[name]

    #    for idx_block in range(len(lst_block)):
    #        label, block = lst_block[idx_block]
    #        print label + ':'

    #        for line in block:
    #            print ' '*line[IDX_LEVEL], line[IDX_TYPE], line[IDX_CODE]
    #        print

def generate_assembly(map_function, map_attribute, f=sys.stdout):
    isr_num = {}
    isr_table = {}
    isr_routine = {}

    if super_verbose == True:
        for name in map_function:
            print("Found function: %s" % name)
    
    #boot section
    f.write(';%s' % ('-' * 60))
    f.write('\n')
    f.write('address 0x000')
    f.write('\n')
    #support init/no init style
    keylist = list(map_function.keys())
    if "init" in list(map_function.keys()):
        f.write('boot:')
        f.write('\n')    
        f.write('  call init')
        f.write('\n')
        # fill address 1/2/3 with nothing
        if vivado_boot_fix == True:
            f.write('; Vivado Hardware Manager workaround - avoid corruption at address 3\n')
            if "loop" in list(map_function.keys()):
                # we can skip over instructions here to save 4 cycles. WOOOOO
                f.write('  jump loop\n')
            else:
                # no loop, so just fill with a no-op
                f.write('  load s0, s0\n')
            f.write('  load s0, s0\n')
            f.write('  load s0, s0\n')
            f.write('\n')
    else:
        if vivado_boot_fix == True:
            f.write('; Vivado Hardware Manager workaround - avoid corruption at address 3\n')
            f.write('  load s0, s0\n')
            f.write('  load s0, s0\n')
            f.write('  load s0, s0\n')
            f.write('  load s0, s0\n')
    #support loop/no loop style
    if "loop" in list(map_function.keys()):
        # loop is present, sort it first
        keylist.insert(0,keylist.pop(keylist.index("loop")))
    else:
        f.write('loop:')
        f.write('\n')    
        f.write('  jump loop')
        f.write('\n')

    f.write('\n')
    
    for name in keylist:
        lst_block = map_function[name]
        label_end = '_end_%s' % name

        #check if isr
        if name in map_attribute:
            attr = map_attribute[name]
            print("attribute: %s" % attr)
            if attr[0] == 'at':
                f.write('address %s' % attr[1])
                f.write('\n')
            elif attr[0] == 'interrupt':
                vec = attr[1].upper()
                print("interrupt attribute had", vec)                
                # yeah, whatever, just use 0x3D0 for now
                #num  = re.search(r'IRQ(\d+)', attr[1].upper()).groups()[0]
                #num  = int(num)
                num = 0
                addr = int(vec, base=0)
                isr_num[name] = num
                isr_table[addr] = name
                isr_routine[name] = addr
            else:
                msg = 'Unknown attribute "%s"' % str(attr)
                raise ParseException(msg)

        #get source file name
        fn_source = ''
        for idx_block in range(len(lst_block)):
            lable, block = lst_block[idx_block]
            for line in block:
                level, lineno, t, code = line
                if t == 'file':
                    fn_source = code[0]
                    break

        f.write(';%s' % ('-' * 60))
        f.write('\n')

        f.write(';%s\n' % fn_source)
        f.write('%s:' % name)
        f.write('\n')

        for idx_block in range(len(lst_block)):
            lable, block = lst_block[idx_block]

            #write label
            f.write(' %s:' % lable)
            f.write('\n')

            for line in block:
                if super_verbose == True:
                    print(line)
                level, lineno, t, code = line
                level = int(level)
                if t not in ['file']:
                    f.write(' ;%s:%d' % (fn_source, lineno))
                    f.write('\n')

                #code fmt label
                if t in ['label']:
                    f.write('  '*level)
                    f.write('  %s:' % code[0]) 
                    f.write('\n')
                    continue
                
                #code fmt endwhile: do_label
                if t in ['endwhile']:
                    f.write('  '*level)
                    f.write('  ;%s' % (t))
                    f.write('\n')

                    f.write('  '*level)
                    f.write('  jump %s' % code[0])
                    f.write('\n')
                    continue

                #code fmt ifjoin: if_label, endif_label
                if t in ['ifjoin']:
                    f.write('  '*level)
                    f.write('  ;%s' % t)
                    f.write('\n')

                    #check jump-jump
                    label_bb = code[-1]
                    block_next_idx = find_blockidx_of_label(lst_block, label_bb)
                    while True:
                        block_next = lst_block[block_next_idx][1][0]
                        if block_next[IDX_TYPE] == 'endif':
                            block_next_idx += 1
                        elif block_next[IDX_TYPE] == 'ifjoin':
                            label_bb = block_next[IDX_CODE][-1]
                            block_next_idx = find_blockidx_of_label(lst_block, label_bb)
                        else:
                            break
                    label_bb

                    f.write('  '*level)
                    f.write('  jump %s' % label_bb)
                    f.write('\n')
                    continue

                elif t in ['endif']:
                    f.write('  '*level)
                    f.write('  ;%s of %s' % (t, code[-1]))
                    f.write('\n')
                    continue

                elif t in ['else']:
                    f.write('  '*level)
                    f.write('  ;%s' % t)
                    f.write('\n')
                    continue

                elif t in ['do', 'endfunc']:
                    f.write('  '*level)
                    f.write('  ;%s' % (t))
                    f.write('\n')
                    continue

                elif t in ['break', 'continue']:
                    f.write('  ' * level)
                    f.write('  ;%s' % (t))
                    f.write('\n')

                    f.write('  ' * level)
                    f.write('  jump %s' % code[0])
                    f.write('\n')

                elif t == 'file':
                    pass
                    #f.write('  ' * level)
                    #f.write('  ;%s' % code[0])
                    #f.write('\n')

                elif t == 'funcdef':
                    f.write('  ' * level)
                    f.write('  ;%s %s (%s)' % \
                            (code[1], code[0], code[2]))
                    f.write('\n')

                elif t == 'funccall':
                    if code[0] in ['enable_interrupt',
                                   'disable_interrupt']:
                        f.write('  ' * level)
                        f.write('  %s' % code[0].replace('_', ' '))
                        f.write('\n')
                    elif code[0] in ['regbank']:
                        print("typeof", type(code[1][0]))
                        try:
                            bank = int(code[1][0])
                            if bank != 0 and bank != 1:
                                msg = 'regbank requires either 0/1: "%s"' % (str(line))
                                raise ParseException(msg)                            
                            f.write('  ' * level)
                            f.write('  %s %s' % (code[0], 'A' if bank == 0 else 'B'))
                            f.write('\n')
                        except Exception as e:
                            raise e
                    elif code[0] in ['input', 'output', 'outputk', 'fetch', 'store']:
                        # check outputk
                        if code[0] == 'outputk':
                            if type(code[1][0]) != int or type(code[1][1]) != int:
                                msg = 'outputk requires constant address and value: "%s"' % (str(line))
                                raise ParseException(msg)                            
                        # check multi-operand.
                        # this allows input(sB.sA, 0x0), with the address specifying the LSB.
                        # Maybe we'll allow a "inputbe" which specifies big-endian input ordering.
                        numops = 1
                        regs = None
                        if type(code[1][1]) == str:
                            regs = code[1][1].split('.')
                            numops = len(regs)
                        if numops > 1:
                            if type(code[1][0]) != int:
                                msg = 'Multi-operand IO/memory operations require constant address: "%s"' % \
                                    (str(line))
                                raise ParseException(msg)
                            regs.reverse()
                            for i in range(len(regs)):
                                f.write('  ' * level)
                                f.write('  %s %s, %d' % (code[0], regs[i], (code[1][0] + i) & 0xFF))
                                f.write('\n')
                        else:
                            if type(code[1][0]) == str:
                                f.write('  ' * level)
                                f.write('  %s %s, (%s)' % (code[0], code[1][1], code[1][0]))
                                f.write('\n')
                            elif type(code[1][0]) == int:
                                f.write('  ' * level)
                                f.write('  %s %s, %d' % (code[0], code[1][1], code[1][0]))
                                f.write('\n')
                    elif code[0] in ['__asm__', 'asm', 'assembly']:
                        f.write('  ' * level)
                        inline_asm = re.search(r'"(.+)"', code[1][0]).groups()[0]
                        f.write('  %s' % inline_asm)
                        f.write('\n')
                    elif code[0] == 'psm':
                        #split text
                        inline_asm = re.search(r'"(.+)"', code[1][0]).groups()[0]
                        #clear params and convert to list
                        other_asm = code[1][0][len(inline_asm) + 2:]
                        other_asm = re.sub(r'^[, ]+', '', other_asm)
                        other_asm = re.sub(r'[ &]+', '', other_asm)
                        other_asm = other_asm.split(',')
                        
                        #replace
                        i = 1
                        for sym in other_asm:
                            inline_asm = inline_asm.replace("%%%d" % i, sym)
                            i += 1

                        f.write('  ' * level)
                        f.write('  %s' % inline_asm)
                        f.write('\n')
                    elif code[0] in labels or code[0] in map_function:
                        f.write('  ' * level)
                        f.write('  call %s' % code[0])
                        f.write('\n')
                    else:
                        msg = 'Unknown instruction "%s"' % (str(line))
                        raise ParseException(msg)

                elif t in ['if', 'else if', 'while', 'dowhile', 'singlewhile']:
                    compare = code[0]
                    param0  = code[1]
                    param1  = code[2]

                    inverted = False
                    if compare[0] == '$':
                        inverted = True
                        compare = compare[1:]
                        if super_verbose == True:
                            print("inverted ", end=' ')
                        
                    if super_verbose == True:
                        print("compare ", compare, " param0 ", param0, " param1 ", param1)
                    # Readability hacks.
                    # Also make more clear what's failing.
                    # These operations aren't natively supported.
                    if compare == '>' or compare == '<=':
                        if super_verbose == True:
                            print("Op %s is not natively supported" % compare)
                            print("Trying to transform it.")
                            print("Param0", param0, "type", type(param0))
                            print("Param1", param1, "type", type(param1))
                        # case str/str is register compare, we can't
                        # do anything easily, we would need a double-flag
                        if (type(param0) == str and \
                            type(param1) == str):
                            print("Register/register compare op", compare,
                                  "cannot be trivially transformed")
                        elif (type(param0) == str and \
                              type(param1) == int):
                            print("converting", "!" if inverted else "",
                                  param0, compare, param1)
                            param1 = param1 + 1
                            if compare == '>':
                                # this is sX > KK (e.g. val > 50)
                                compare = '<'
                                inverted = True if not inverted else False
                            else:
                                # this is sX <= KK (e.g. val <= 50)
                                compare = '<'
                            print("converted to", "!" if inverted else "",
                                  param0, compare, param1)
                    #check if const value
                    if type(param0) == int and \
                            type(param1) == int:
                        res = {'val':0}
                        text = 'val = %s %s %s' % (param0, compare, param1)
                        exec(text, {}, res)
                        if res['val'] == True or res['val'] != 0:
                            param0  = 's0'
                            if inverted:
                                compare = '!='
                            else:
                                compare = '=='
                            param1  = 's0'
                        else:
                            param0  = 's0'
                            if inverted:
                                compare = '=='
                            else:
                                compare = '!='
                            param1  = 's0'
                    elif type(param0) == int and \
                            type(param1) != int:
                        msg = 'Param0 must be register when Param1 is digit! "%s"' % \
                                (str(line))
                        raise ParseException(msg)

                    label_t = code[3]
                    label_f = code[4]

                    f.write('  ' * level)
                    f.write('  ;%s (%s %s %s), %s, %s' % \
                            (t, param0, compare, param1, label_t, label_f))
                    f.write('\n')

                    f.write('  ' * level)                        
                    if compare in ['==', '!=', '<', '>=']:
                        if param0 == 'Z' or param0 == 'C':
                            if super_verbose == True:
                                print("condition check: ", param0, compare, param1)
                            if param1 != 0 or compare == '<' or compare == '>=':
                                msg = 'Condition checks are only == 0 or != 0'
                                raise ParseException(msg)
                            # we can handle the inversion here
                            if inverted:
                                if compare == '==':
                                    compare = '!='
                                else:
                                    compare = '=='
                                inverted = False
                            
                        # check double register compare
                        # I should extend this to arbitrary length.
                        elif len(param0.split('.')) > 1:
                            regs = param0.split('.')
                            # reverse the regs order, since they're specified MSB-first
                            regs.reverse()
                            operands = []
                            nregs = len(param0.split('.'))
                            print("multi-register compare: %d regs" % nregs)
                            if type(param1) == str:
                                if len(param1.split('.')) != nregs:
                                    msg = 'Multi-register operations need equal # of operands "%s"' % (str(line))
                                    raise ParseException(msg)
                                operands = param1.split('.')
                                # reverse operands order
                                operands.reverse()
                            else:
                                for num in range(nregs):
                                    operands.append((param1 >> 8*num) & 0xFF)
                            print("regs: ", regs)
                            print("operands: ", operands)
                            for num in range(nregs):
                                if num == 0:
                                    f.write('  compare %s, %s' % (regs[num], str(operands[num])))
                                else:
                                    f.write('\n')
                                    f.write('  ' * level)
                                    f.write('  comparecy %s, %s' % (regs[num], str(operands[num])))        
                        else:
                            f.write('  compare %s, %s' % (str(param0), str(param1)))
                    # ^ is the opposite of & for a bit test
                    elif compare in ['&','^']:
                        f.write('  test %s, %s' % (str(param0), str(param1)))
                    elif compare in ['--']:
                        if len(param0.split('.')) > 1:
                            print("multi register subtract-test:", param0, compare)
                            regs = param0.split('.')
                            regs.reverse()
                            for num in range(len(regs)):
                                if num == 0:                                    
                                    f.write('  sub %s, 1' % (str(regs[num])))
                                else:
                                    f.write('\n')
                                    f.write('  ' * level)
                                    f.write('  subcy %s, 0' % (str(regs[num])))
                        else:
                            if super_verbose == True:
                                print("subtract-test")
                            f.write('  sub %s, 1' % (str(param0)))
                        
                    f.write('\n')

                    if param0 =='Z' or param0 == 'C':
                        if compare == '==':
                            # equal zero
                            flage_t = 'N'+param0
                            flage_f = param0
                        else:
                            flage_t = param0
                            flage_f = 'N'+param0
                    elif compare == '==':
                        flage_t = 'Z'
                        flage_f = 'NZ'
                    elif compare == '!=':
                        flage_t = 'NZ'
                        flage_f = 'Z'
                    elif compare == '<':
                        flage_t = 'C'
                        flage_f = 'NC'
                    elif compare == '>=':
                        flage_t = 'NC'
                        flage_f = 'C'
                    #test
                    elif compare == '&':
                        flage_t = 'NZ'
                        flage_f = 'Z'
                    elif compare == '^':
                        flage_t = 'Z'
                        flage_f = 'NZ'
                    elif compare == '--':
                        if super_verbose == True:
                            print("subtract-test: ", end=' ')
                        # carry test: this is s0--. True if not C.
                        if param1 == -1:
                            if super_verbose == True:
                                print("test-subtract")
                            flage_t = 'NC'
                            flage_f = 'C'
                        # carry test: this is !(s0--). True if C.
                        elif param1 == -2:
                            if super_verbose == True:
                                print("test-subtract inverted")
                            flage_t = 'C'
                            flage_f = 'NC'
                        elif param1 == 1:
                            # inverted: matches if Z, fails if NZ
                            if super_verbose == True:
                                print("subtract-test inverted")
                            flage_t = 'Z'
                            flage_f = 'NZ'
                        else:
                            # if (--s0) matches if NZ, fails if Z
                            flage_t = 'NZ'
                            flage_f = 'Z'
                    else:
                        msg = 'Not support "%s"' % str(line)
                        raise ParseException(msg)

                    #optimize jump
                    if idx_block + 1 < len(lst_block):
                        next_block_label = lst_block[idx_block + 1][0]
                        #check jump-jump
                        label_bb = label_f
                        while True:
                            block_next_idx = find_blockidx_of_label(lst_block, label_bb)
                            block_next = lst_block[block_next_idx][1][0]
                            if block_next[IDX_TYPE] == 'ifjoin':
                                label_bb = block_next[IDX_CODE][-1]
                            else:
                                break
                        label_f = label_bb

                        label_bb = label_t
                        while True:
                            block_next_idx = find_blockidx_of_label(lst_block, label_bb)
                            block_next = lst_block[block_next_idx][1][0]
                            if block_next[IDX_TYPE] == 'ifjoin':
                                label_bb = block_next[IDX_CODE][-1]
                            else:
                                break
                        label_t = label_bb

                        if next_block_label == label_f:
                            f.write('  ' * level)
                            f.write('  jump %s, %s' % (flage_t, label_t))
                            f.write('\n')
                            continue

                        elif next_block_label == label_t:
                            f.write('  ' * level)
                            f.write('  jump %s, %s' % (flage_f, label_f))
                            f.write('\n')
                            continue

                    f.write('  ' * level)
                    f.write('  jump %s, %s' % (flage_f, label_f))
                    f.write('\n')

                    f.write('  ' * level)
                    f.write('  jump %s, %s' % (flage_t, label_t))
                    f.write('\n')

                elif t == 'goto':
                    f.write('  ' * level)
                    f.write('  ;end of while')
                    f.write('\n')
                    f.write('  ' * level)
                    f.write('  jump %s' % code[0])
                    f.write('\n')

                elif t == 'assign':
                    assign_type = code[0]
                    param0  = code[1]
                    param1  = code[2]
                    if len(param0.split('.')) > 1:
                        # paired register math
                        print("multi register assembly:", param0, assign_type, param1)
                        regs = param0.split('.')
                        regs.reverse()
                        nregs = len(regs)
                        operands = []
                        if super_verbose == True:
                            print(type(param1))
                        if type(param1) == str:
                            print("register/register operation")
                            if len(param1.split('.')) != nregs:
                                #  msg = 'Paired registers operations need pairs of operands "%s"' % (str(line))
                                #  raise ParseException(msg)                                
                                print("warning: paired register operations with fewer operands (%s)" % (str(line)))
                                print("         padding missing operands with 0 (this is OK, just letting you know)")
                                if len == 0:
                                    operands.append(param1)
                                else:
                                    operands=param1.split('.')
                                    operands.reverse()
                                for num in range(nregs-len(operands)):
                                    operands.append(0)
                                print("operands: ", operands)
                            else:
                                operands = param1.split('.')
                                operands.reverse()
                        else:
                            for num in range(nregs):
                                operands.append((param1>>8*num) & 0xFF)
                        if assign_type == '=':
                            for num in range(nregs):                                
                                f.write('  ' * level)
                                f.write('  move %s, %s' % (regs[num], str(operands[num])))
                                f.write('\n')
                        elif assign_type == '+=':
                            for num in range(nregs):
                                f.write('  ' * level)
                                if num == 0:
                                    f.write('  add %s, %s' % (regs[num], str(operands[num])))
                                else:
                                    f.write('  addcy %s, %s' % (regs[num], str(operands[num])))
                                f.write('\n')
                        elif assign_type == '-=':
                            for num in range(nregs):
                                f.write('  ' * level)
                                if num == 0:
                                    f.write('  sub %s, %s' % (regs[num], str(operands[num])))
                                else:
                                    f.write('  subcy %s, %s' % (regs[num], str(operands[num])))
                                f.write('\n')
                        elif assign_type == '<<=':
                            if type(operands[0]) == str:
                                msg = 'Shifts must be a constant value'
                                raise ParseException(msg)
                            while param1 > 0:
                                for num in range(nregs):
                                    f.write('  ' * level)
                                    if num == 0:
                                        f.write('  sl0 %s' % regs[num])
                                    else:
                                        f.write('  sla %s' % regs[num])      
                                    f.write('\n')
                                param1 -= 1
                        elif assign_type == '>>=':
                            if type(operands[0]) == str:
                                msg = 'Shifts must be a constant value'
                                raise ParseException(msg)
                            while param1 > 0:
                                for num in range(nregs):
                                    f.write('  ' * level)
                                    if num == 0:
                                        f.write('  sr0 %s' % regs[num])
                                    else:
                                        f.write('  sra %s' % regs[num])
                                    f.write('\n')
                                param1 -= 1
                        elif assign_type == '&=' or assign_type == '|=' or assign_type == '^=':
                            if assign_type == '&=':
                                op = 'and'
                            elif assign_type == '|=':
                                op = 'or'
                            elif assign_type == '^=':
                                op = 'xor'
                            for num in range(nregs):
                                # figure out if we need this
                                # Note that flags will technically
                                # differ if we skip an op, but
                                # there's no way to do a multi-register
                                # bitwise operation that combines flags anyway.
                                need_op = True
                                if type(operands[num]) == str:
                                    need_op = True
                                elif op == 'and' and operands[num] == 255:
                                    need_op = False
                                elif op == 'or' and operands[num] == 0:
                                    need_op = False
                                elif op == 'xor' and operands[num] == 0:
                                    need_op = False
                                if need_op == True:
                                    f.write('  ' * level)
                                    f.write('  %s %s, %s' % (op, regs[num], str(operands[num])))
                                    f.write('\n')
                                else:
                                    print("Note: ignoring '%s %s %s' NOP" % (regs[num], assign_type, operands[num]))
                                    print("      in multi-register operation.")
                                    
                        else:
                            msg = 'Unknown operator "%s"' % (str(line))
                            raise ParseException(msg)                            
                    elif assign_type == '=':
                        f.write('  ' * level)
                        f.write('  move %s, %s' % (param0, str(param1)))
                        f.write('\n')
                    elif assign_type == '+=':
                        f.write('  ' * level)
                        f.write('  add %s, %s' % (param0, str(param1)))
                        f.write('\n')
                    elif assign_type == '-=':
                        f.write('  ' * level)
                        f.write('  sub %s, %s' % (param0, str(param1)))
                        f.write('\n')
                    elif assign_type == '<<=':
                        while param1 > 0:
                            f.write('  ' * level)
                            f.write('  sl0 %s' % param0)
                            f.write('\n')
                            param1 -= 1
                    elif assign_type == '>>=':
                        while param1 > 0:
                            f.write('  ' * level)
                            f.write('  sr0 %s' % param0)
                            f.write('\n')
                            param1 -= 1
                    elif assign_type == '&=':
                        f.write('  ' * level)
                        f.write('  and %s, %s' % (param0, str(param1)))
                        f.write('\n')
                    elif assign_type == '|=':
                        f.write('  ' * level)
                        f.write('  or %s, %s' % (param0, str(param1)))
                        f.write('\n')
                    elif assign_type == '^=':
                        f.write('  ' * level)
                        f.write('  xor %s, %s' % (param0, str(param1)))
                        f.write('\n')
                    else:
                        msg = 'Unknown operator "%s"' % (str(line))
                        raise ParseException(msg)

                elif t == 'return':
                    f.write('  ' * level)
                    if code:
                        f.write('  returni %s' % code)
                        f.write('\n')
                    else:
                        f.write('  return')
                        f.write('\n')

                else:
                    msg = 'Unknown instruction "%s"' % (str(line))
                    raise ParseException(msg)


            f.write('\n')
            pass

        #end of function
        f.write('%s:' % label_end)
        f.write('\n')

        if name in isr_routine:
            num = isr_num[name]
            isr_clr_addr = num / 8
            isr_clr_data = 1 << (num % 8)

            # no irq autoclearing,
            # maybe add a way to include this
            # f.write('  ;auto clear IRQ%d, offset = 0x%x, value = 0x%02X\n' % \
            #        (num, isr_clr_addr, isr_clr_data))
            # f.write('  move sF, %d\n' % isr_clr_data)
            # f.write('  output sF, %d\n' % (BASEADDR_INTC_CLEAR + isr_clr_addr))
            f.write('  returni enable')
        elif name == "loop":
            f.write('  jump loop')
        elif name in labels:
            # do nothing, it's a label, it has no return
            pass
        else:
            f.write('  return')
        f.write('\n')

        f.write('\n')
        f.write('\n')
        pass

    f.write('\n')
    f.write(';ISR')
    f.write('\n')
    for addr in sorted(isr_table):
        f.write(';IRQ%d' % isr_num[isr_table[addr]])
        f.write('\n')
        f.write('address 0x%03X' % addr)
        f.write('\n')
        f.write('jump    %s' % isr_table[addr])
        f.write('\n')
    pass

usage = '''\
usage : %s [option] file

 -l         add Vivado JTAG loader workaround
 -h         help
 -I         include path
 -o <file>  output file name
 -g         dump mid-information
''' % os.path.split(sys.argv[0])[1]

def parse_commandline():
    format_s = 'I:o:ghlv'
    format_l = []
    opts, args = getopt.getopt(sys.argv[1:], format_s, format_l)

    map_options = {}
    for (k, v) in opts:
        if k == '-I':
            if k not in map_options:
                map_options[k] = []
            map_options[k].append(v)
        else:
            map_options[k] = v

    if '-h' in map_options:
        print(usage)
        sys.exit(-1)        

    return map_options, args

if __name__ == '__main__':
    try:
        map_options, lst_args = parse_commandline()
        vivado_boot_fix = False
        if '-l' in map_options:
            vivado_boot_fix = True
        if len(lst_args) == 0:
            print(usage)
            sys.exit(-1)

        if '-v' in map_options:
            super_verbose = True
            
        if '-o' not in map_options:
            fn_name = os.path.split(lst_args[0])[1]
            fn_out = os.path.splitext(fn_name)[0] + '.s'
            map_options['-o'] = fn_out
        else:
            fn_out = os.path.splitext(map_options['-o'])[0] + '.s'

        map_options['path_noext'] = fn_out[:-2]

        #preprocess
        args = ['mcpp.exe']

        #add current
        pblaze_cc_path = os.path.realpath(sys.argv[0])
        if not os.path.isfile(pblaze_cc_path):
            pblaze_cc_path = sys.executable
        if os.path.isfile(pblaze_cc_path):
            args.append('-I')
            args.append(os.path.dirname(pblaze_cc_path))

        if '-I' in map_options:
            for path in map_options['-I']:
                args.append('-I')
                args.append(path)
            
#        args.extend(['-e', 'utf-8', '-z', lst_args[0]])
        args.extend(['-e', 'utf-8', '-D', 'PBLAZE_CC', lst_args[0]])
        for arg in args:
            print("preprocessor: %s" % arg)
        (returncode, stdout_text, stderr_text) = popen(args)
        if returncode == 0:
            if '-g' in map_options:
                print('wrote %d bytes to "mcpp.stdout"' % len(stdout_text))
                fn = '%s.mcpp.tmp' % map_options['path_noext']
                file_put_contents(fn, stdout_text)
        else:
            print(stderr_text)
            raise ParseException('mcpp.exe error')

        #let lineno correct
        lst_line = resolve_lineno(stdout_text)
        stdout_text = '\n'.join(lst_line)

        #format style
        # The 'j' option here breaks up one-line condition blocks.
        # - this is needed to process single-line conditions (e.g. if (a) c = d;)
        #
        # The 'f' option here inserts lines between unrelated blocks:
        # - this is needed to identify single-line whiles versus do-whiles.
        #
        # -p pads around operators to help Python
        args = ['astyle.exe', '-f', '-j', '-p','--style=gnu', '--suffix=none']
        (returncode, stdout_text, stderr_text) = popen(args, stdout_text)
        if returncode == 0:
            if '-g' in map_options:
                print('wrote %d bytes to "astyle.stdout"' % len(stdout_text))
                fn = '%s.astyle.tmp' % map_options['path_noext']
                file_put_contents(fn, stdout_text)
        else:
            print(stderr_text)
            raise ParseException('astyle.exe error')

        #parse text
        text = stdout_text
        info = parse(text)

        #group lines
        (map_function, map_attribute) = convert_list_to_block(info)
        if '-g' in map_options:
            fn = '%s.pass1.tmp' % map_options['path_noext']
            f = open(fn, 'w')
            dump_blocks(map_function, f)
            f.close()

        #expand loop
        convert_condition_to_ifgoto2(map_function)
        if '-g' in map_options:
            fn = '%s.pass2.tmp' % map_options['path_noext']
            f = open(fn, 'w')
            dump_blocks(map_function, f)
            f.close()

        #dump meta information
        f = open(map_options['-o'], 'w')
        f.write(';#!pblaze-cc source : %s\n' % lst_args[0])

        #get source file time
        t = os.stat(lst_args[0])
        f.write(';#!pblaze-cc create : %s\n' % time.ctime(t.st_ctime))
        f.write(';#!pblaze-cc modify : %s\n' % time.ctime(t.st_mtime))

        #dump assembly result
        print('using BASEADDR_INTC_CLEAR = 0x%02x' % BASEADDR_INTC_CLEAR)
        generate_assembly(map_function, map_attribute, f)
        print('wrote %d bytes to "%s"' % (f.tell(), map_options['-o']))
        f.close()


    except ParseException as e:
        traceback.print_exc()
        print(e.msg)

    print()



