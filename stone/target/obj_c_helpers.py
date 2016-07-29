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
    is_float_type,
    is_list_type,
    is_numeric_type,
    is_string_type,
    is_struct_type,
    is_timestamp_type,
    is_tag_ref,
    is_union_type,
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
    Boolean: 'DbxBoolSerializer',
    Bytes: 'DbxNSDataSerializer',
    Float32: 'DbxNSNumberSerializer',
    Float64: 'DbxNSNumberSerializer',
    Int32: 'DbxNSNumberSerializer',
    Int64: 'DbxNSNumberSerializer',
    List: 'DbxArraySerializer',
    String: 'DbxStringSerializer',
    Timestamp: 'DbxNSDateSerializer',
    UInt32: 'DbxNSNumberSerializer',
    UInt64: 'DbxNSNumberSerializer',
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


def fmt_camel(name, upper_first=False, reserved=True, prefixes=False):
    name = str(name)
    words = [word.capitalize() for word in split_words(name)]
    if not upper_first:
        words[0] = words[0].lower()
    ret = ''.join(words)

    if reserved:
        if ret.lower() in _reserved_words:
            ret += '_'
        # properties can't begin with certain keywords
        for reserved_prefix in _reserved_prefixes:
            if ret.lower().startswith(reserved_prefix):
                new_prefix = 'the' if not upper_first else 'The'
                ret = new_prefix + ret[0].upper() + ret[1:]
                continue
    return ret

def fmt_enum_name(field_name, union):
    return '{}{}{}'.format(fmt_camel_upper(union.namespace.name), fmt_camel_upper(union.name), fmt_camel_upper(field_name))

def fmt_camel_upper(name, reserved=True):
    return fmt_camel(name, upper_first=True, reserved=reserved)

def fmt_public_name(name):
    return fmt_camel_upper(name)


def fmt_class(name):
    return fmt_camel_upper(name)


def fmt_class_type(data_type):
    data_type, nullable = unwrap_nullable(data_type)

    if is_user_defined_type(data_type):
        result = '{}'.format(fmt_class_prefix(data_type))
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
        result = 'Dbx{}{} *'.format(fmt_class(data_type.namespace.name), fmt_class(data_type.name))
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


def fmt_class_prefix(data_type):
    return 'Dbx{}{}'.format(fmt_class(data_type.namespace.name), fmt_class(data_type.name))


def fmt_literal(example_value, data_type):    
    data_type, nullable = unwrap_nullable(data_type)

    result = example_value

    if is_user_defined_type(data_type):
        obj_args = []

        if is_union_type(data_type):
            example_tag = example_value['.tag']



            for field in data_type.all_fields:
                if field.name == example_tag:
                    if not is_void_type(field.data_type):
                        if field.name in example_value:
                            obj_args.append((fmt_var(field.name), fmt_literal(example_value[field.name], field.data_type)))
                        else:
                            obj_args.append((fmt_var(field.name), fmt_literal(example_value, field.data_type)))

            result = fmt_func_call(fmt_alloc_call(fmt_class_prefix(data_type)),
                'initWith{}'.format(fmt_camel_upper(example_value['.tag'])), fmt_func_args(obj_args))
        else:
            if data_type.has_enumerated_subtypes():
                for tags, subtype in data_type.get_all_subtypes_with_tags():
                    assert len(tags) == 1, tags
                    tag = tags[0]
                    if tag == example_value['.tag']:
                        result = fmt_literal(example_value, subtype)
            else:
                for field in data_type.all_fields:
                    if field.name in example_value:
                        obj_args.append((fmt_var(field.name), fmt_literal(example_value[field.name], field.data_type)))
                    else:
                        if not is_void_type(field.data_type):
                            obj_args.append((fmt_var(field.name), fmt_default(field.data_type)))
                result = fmt_func_call(fmt_alloc_call(fmt_class_prefix(data_type)),
                    'initWith{}'.format(fmt_camel_upper(data_type.all_fields[0].name)), fmt_func_args(obj_args))
    elif is_list_type(data_type):
        if example_value:
            result = '@[{}]'.format(fmt_literal(example_value[0], data_type.data_type))
        else:
            result = 'nil'
    elif is_numeric_type(data_type):
        if is_float_type(data_type):
            result = '[NSNumber numberWithDouble:{}]'.format(example_value)
        elif isinstance(data_type, (UInt64, Int64)):
            result = '[NSNumber numberWithLong:{}]'.format(example_value)
        else:
            result = '[NSNumber numberWithInt:{}]'.format(example_value)
    elif is_timestamp_type(data_type):
        result = '[DbxNSDateSerializer deserialize:@"{}" dateFormat:@"{}"]'.format(example_value, data_type.format)
    elif is_string_type(data_type):
        result = '@"{}"'.format(result)
    elif is_boolean_type(data_type):
        result = '@YES' if bool(example_value) else '@NO'

    return str(result)


def fmt_default(data_type):
    data_type, nullable = unwrap_nullable(data_type)

    result = 'DEFAULT'

    if nullable:
        return 'nil'

    if is_user_defined_type(data_type):
        result = fmt_func_call(fmt_alloc_call(fmt_class_prefix(data_type)), 'init', [])
    elif is_list_type(data_type):
        result = fmt_func_call(fmt_alloc_call('NSArray'), 'init', [])
    elif is_numeric_type(data_type):
        if is_float_type(data_type):
            result = '[NSNumber numberWithDouble:5]'
        else:
            result = '[NSNumber numberWithInt:5]'
    elif is_timestamp_type(data_type):
        result = '[[NSDateFormatter new] setDateFormat:[self convertFormat:@"test"]]'
    elif is_string_type(data_type):
        result = '@"teststring"'
    elif is_boolean_type(data_type):
        result = '@YES'

    return result


def fmt_validator(data_type):
    return _validator_table.get(data_type.__class__, fmt_class(data_type.name))


def fmt_serial_obj(data_type):
    data_type, nullable = unwrap_nullable(data_type)

    if is_user_defined_type(data_type):
        result = 'Dbx{}{}Serializer'.format(fmt_camel_upper(data_type.namespace.name), fmt_class(data_type.name))
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


def fmt_default_value(field):
    if is_tag_ref(field.default):
        return '[[{} alloc] initWith{}]'.format(
            fmt_class_prefix(field.default.union_data_type),
            fmt_class(field.default.tag_name))
    elif is_numeric_type(field.data_type):
        return '[NSNumber numberWithInt:{}]'.format(field.default)
    elif is_boolean_type(field.data_type):
        if field.default:
            bool_str = 'YES'
        else:
            bool_str = 'NO'
        return '@{}'.format(bool_str)
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
