from __future__ import absolute_import, division, print_function, unicode_literals

import pprint

from stone.data_type import (
    Boolean,
    Bytes,
    Float32,
    Float64,
    Int32,
    Int64,
    List,
    String,
    Timestamp,
    UInt32,
    UInt64,
    Void,
    is_alias,
    is_boolean_type,
    is_list_type,
    is_numeric_type,
    is_string_type,
    is_struct_type,
    is_timestamp_type,
    is_tag_ref,
    is_user_defined_type,
    is_void_type,
    unwrap_nullable,
)
from .helpers import split_words

# This file defines *stylistic* choices for Swift
# (ie, that class names are UpperCamelCase and that variables are lowerCamelCase)


_primitive_table = {
    Boolean: 'NSNumber *',
    Bytes: 'NSData',
    Float32: 'NSNumber *',
    Float64: 'NSNumber *',
    Int32: 'NSNumber *',
    Int64: 'NSNumber *',
    List: 'NSArray',
    String: 'NSString *',
    Timestamp: 'NSDate *',
    UInt32: 'NSNumber *',
    UInt64: 'NSNumber *',
    Void: 'void',
}


_serial_table = {
    Boolean: 'BoolSerializer',
    Bytes: 'NSDataSerializer',
    Float32: 'NSNumberSerializer',
    Float64: 'NSNumberSerializer',
    Int32: 'NSNumberSerializer',
    Int64: 'NSNumberSerializer',
    List: 'ArraySerializer',
    String: 'StringSerializer',
    Timestamp: 'NSDateSerializer',
    UInt32: 'NSNumberSerializer',
    UInt64: 'NSNumberSerializer',
}


_validator_table = {
    Float32: 'numericValidator',
    Float64: 'numericValidator',
    Int32: 'numericValidator',
    Int64: 'numericValidator',
    List: 'arrayValidator',
    String: 'stringValidator',
    UInt32: 'numericValidator',
    UInt64: 'numericValidator',
}


_true_primitives = {
    Boolean,
    # Float64,
    # UInt32,
    # UInt64,
}


_reserved_words = {
    'auto',
    'else',
    'long',
    'switch',
    'break',
    'enum',
    'register',
    'typedef',
    'case',
    'extern',
    'return',
    'union',
    'char',
    'float',
    'short',
    'unsigned',
    'const',
    'for',
    'signed',
    'void',
    'continue',
    'goto',
    'sizeof',
    'volatile',
    'default',
    'if',
    'static',
    'while',
    'do',
    'int',
    'struct',
    '_Packed',
    'double',
    'protocol',
    'interface',
    'implementation',
    'NSObject',
    'NSInteger',
    'NSNumber',
    'CGFloat',
    'property',
    'nonatomic',
    'retain',
    'strong',
    'weak',
    'unsafe_unretained',
    'readwrite',
    'description',
    'id',
}


_reserved_prefixes = {
    'copy',
    'new',
}


def fmt_obj(o):
    assert not isinstance(o, dict), "Only use for base type literals"
    if o is True:
        return 'true'
    if o is False:
        return 'false'
    if o is None:
        return 'nil'
    return pprint.pformat(o, width=1)


def fmt_camel(name, upper_first=False):
    name = str(name)
    words = [word.capitalize() for word in split_words(name)]
    if not upper_first:
        words[0] = words[0].lower()
    ret = ''.join(words)
    if ret.lower() in _reserved_words:
        ret += '_'
    # properties can't begin with certain keywords
    for reserved_prefix in _reserved_prefixes:
        if ret.lower().startswith(reserved_prefix):
            new_prefix = 'the' if not upper_first else 'The'
            ret = new_prefix + ret[0].upper() + ret[1:]
            continue
    return ret

def fmt_camel_upper(name):
    return fmt_camel(name, upper_first=True)

def fmt_public_name(name):
    return fmt_camel_upper(name)


def fmt_class(name):
    return fmt_camel_upper(name)


def fmt_class_type(data_type):
    data_type, nullable = unwrap_nullable(data_type)

    if is_user_defined_type(data_type):
        result = '{}'.format(fmt_class(data_type.name))
    else:
        result = _primitive_table.get(data_type.__class__, fmt_class(data_type.name))
        
        if is_list_type(data_type):
            data_type, _ = unwrap_nullable(data_type.data_type)
            result = result + '<{}>'.format(fmt_type(data_type))

    return result 


def fmt_func(name):
    return fmt_camel(name)


def fmt_type(data_type, tag=False, has_default=False):
    data_type, nullable = unwrap_nullable(data_type)

    if is_user_defined_type(data_type):
        result = '{} *'.format(fmt_class(data_type.name))
    else:
        result = _primitive_table.get(data_type.__class__, fmt_class(data_type.name))
        
        if is_list_type(data_type):
            data_type, _ = unwrap_nullable(data_type.data_type)
            if data_type.__class__ in _true_primitives:
                if nullable or has_default:
                    result = result + ' * _Nullable'
                else:
                    result = result + ' * _Nonnull'
            else:
                result = result + '<{}> *'.format(fmt_type(data_type)) 
    
    if tag:
        if nullable or has_default:
            result += ' _Nullable'
        elif not is_void_type(data_type):
            result += ' _Nonnull'

    return result


def fmt_validator(data_type):
    return _validator_table.get(data_type.__class__, fmt_class(data_type.name))


def fmt_serial_obj(data_type):
    data_type, nullable = unwrap_nullable(data_type)

    if is_user_defined_type(data_type):
        result = '{}Serializer'.format(fmt_class(data_type.name))
    else:
        result = _serial_table.get(data_type.__class__, fmt_class(data_type.name))

    return result


def fmt_func_args(arg_str_pairs, standard=False):
    result = []
    first_arg = True
    for arg_name, arg_value in arg_str_pairs:
        if first_arg and not standard:
            result.append('{}'.format(arg_value))
            first_arg = False
        else:
            result.append('{}:{}'.format(arg_name, arg_value))
    return ' '.join(result)


def fmt_func_args_declaration(arg_str_pairs):
    result = []
    first_arg = True
    for arg_name, arg_type in arg_str_pairs:
        if first_arg:
            result.append('({}){}'.format(arg_type, arg_name))
            first_arg = False
        else:
            result.append('{}:({}){}'.format(arg_name, arg_type, arg_name))
    return ' '.join(result)


def fmt_func_args_from_fields(args):
    result = []
    first_arg = True
    for arg in args:
        if first_arg:
            result.append('({}){}'.format(fmt_type(arg.data_type), fmt_var(arg.name)))
            first_arg = False
        else:
            result.append('{}:({}){}'.format(fmt_var(arg.name), fmt_type(arg.data_type), fmt_var(arg.name)))
    return ' '.join(result)


def fmt_func_call(func_caller, func_name, func_args):
    if func_args:
        result = '[{} {}:{}]'.format(func_caller, func_name, func_args)
    else:
        result = '[{} {}]'.format(func_caller, func_name)

    return result

def fmt_alloc_call(class_name):
    return '[{} alloc]'.format(class_name)


def fmt_struct_init_args(data_type, namespace=None):
    args = []
    for field in data_type.all_fields:
        name = fmt_var(field.name)
        value = fmt_type(field.data_type, tag=True)
        field_type = field.data_type
        if is_nullable_type(field_type):
            field_type = field_type.data_type
            nullable = True
        else:
            nullable = False

        if field.has_default:
            if is_union_type(field_type):
                default = '.{}'.format(fmt_class(field.default.tag_name))
            else:
                default = fmt_obj(field.default)
            value += ' = {}'.format(default)
        elif nullable:
            value += ' = nil'
        arg = (name, value)
        args.append(arg)
    return args


def fmt_default_value(field):
    if is_tag_ref(field.default):
        return '[[{} alloc] initWith{}]'.format(
            fmt_class(field.default.union_data_type.name),
            fmt_class(field.default.tag_name))
    elif is_numeric_type(field.data_type):
        return '[NSNumber numberWithInt:{}]'.format(field.default)
    elif is_boolean_type(field.data_type):
        if field.default:
            bool_str = 'YES'
        else:
            bool_str = 'NO'
        return '[NSNumber numberWithBool:{}]'.format(bool_str)
    else:
        raise TypeError('Can\'t handle default value type %r' % type(field.data_type))


def fmt_signature(func_name, fields, return_type, class_method=False):
    modifier = '-' if not class_method else '+'
    if fields:
        result = '{} ({}){}:{};'.format(modifier, return_type, func_name, fields)
    else:
        result = '{} ({}){};'.format(modifier, return_type, func_name)

    return result


def is_primitive_type(data_type):
    data_type, _ = unwrap_nullable(data_type)
    return data_type.__class__ in _true_primitives


def fmt_var(name):
    return fmt_camel(name)


def fmt_property(field, is_union=False):
    attrs = ['nonatomic']
    base_string = '@property ({}) {} {};'

    return base_string.format(', '.join(attrs), fmt_type(field.data_type, tag=True), fmt_var(field.name))


def fmt_import(header_file):
    return '#import "{}.h"'.format(header_file)

def fmt_property_str(prop_name, prop_type):
    attrs = ['nonatomic']
    base_string = '@property ({}) {} {};'
    return base_string.format(', '.join(attrs), prop_type, prop_name)


def is_ptr_type(data_type):
    data_type, _ = unwrap_nullable(data_type)
    if data_type.__class__ in _true_primitives:
        type_name = 'NSInteger'
    type_name = _primitive_table.get(data_type.__class__, fmt_class(data_type.name))
    return type_name[-1] == '*' or is_struct_type(data_type) or is_list_type(data_type)
