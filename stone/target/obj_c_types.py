from __future__ import absolute_import, division, print_function, unicode_literals

import argparse
import json
import os
import shutil

from collections import defaultdict
from contextlib import contextmanager

from stone.data_type import (
    is_boolean_type,
    is_list_type,
    is_nullable_type,
    is_numeric_type,
    is_string_type,
    is_struct_type,
    is_timestamp_type,
    is_union_type,
    is_user_defined_type,
    is_void_type,
    unwrap_nullable,
)
from stone.target.obj_c_helpers import (
    fmt_alloc_call,
    fmt_camel,
    fmt_camel_upper,
    fmt_class,
    fmt_class_prefix,
    fmt_class_type,
    fmt_default_value,
    fmt_enum_name,
    fmt_func,
    fmt_func_args,
    fmt_func_args_declaration,
    fmt_func_args_from_fields,
    fmt_func_call,
    fmt_import,
    fmt_property,
    fmt_property_str,
    fmt_public_name,
    fmt_routes_class,
    fmt_route_obj_class,
    fmt_route_var,
    fmt_serial_class,
    fmt_serial_obj,
    fmt_signature,
    fmt_type,
    fmt_validator,
    fmt_var,
    is_primitive_type,
    is_ptr_type,
)
from stone.target.obj_c import (
    base,
    comment_prefix,
    ObjCBaseGenerator,
    undocumented,
)


_cmdline_parser = argparse.ArgumentParser(prog='obj-c-types-generator')
_cmdline_parser.add_argument(
    '-r',
    '--route-method',
    help=('A string used to construct the location of an Objective C method for a '
          'given route; use {ns} as a placeholder for namespace name and '
          '{route} for the route name.'),
)


class ObjCTypesGenerator(ObjCBaseGenerator):
    """Generates Obj C modules to represent the input Stone spec."""

    cmdline_parser = _cmdline_parser
    def generate(self, api):
        """
        Generates a module for each namespace.

        Each namespace will have Obj C classes to represent data types and
        routes in the Stone spec.
        """
        rsrc_folder = os.path.join(os.path.dirname(__file__), 'obj_c_rsrc')
        rsrc_output_folder = os.path.join(self.target_folder_path, 'Resources')

        self.logger.info('Copying DbxStoneValidators.{h,m} to output folder')
        shutil.copy(os.path.join(rsrc_folder, 'DbxStoneValidators.h'),
                    rsrc_output_folder)
        shutil.copy(os.path.join(rsrc_folder, 'DbxStoneValidators.m'),
                    rsrc_output_folder)
        self.logger.info('Copying DbxStoneSerializers.{h,m} to output folder')
        shutil.copy(os.path.join(rsrc_folder, 'DbxStoneSerializers.h'),
                    rsrc_output_folder)
        shutil.copy(os.path.join(rsrc_folder, 'DbxStoneSerializers.m'),
                    rsrc_output_folder)
        self.logger.info('Copying DbxStoneBase.{h,m} to output folder')
        shutil.copy(os.path.join(rsrc_folder, 'DbxStoneBase.h'),
                    rsrc_output_folder)
        shutil.copy(os.path.join(rsrc_folder, 'DbxStoneBase.m'),
                    rsrc_output_folder)

        for namespace in api.namespaces.values():
            self._generate_namespace_types(namespace)

            if namespace.routes:
                self._generate_route_objects_m(api.route_schema, namespace)
                self._generate_route_objects_h(api.route_schema, namespace)

    def _generate_namespace_types(self, namespace):
        """Creates Obj C argument, error, serializer and deserializer types
        for the given namespace."""
        ns_name = fmt_public_name(namespace.name)
        output_path = os.path.join('ApiObjects', ns_name)

        for data_type in namespace.linearize_data_types():
            class_name = fmt_class_prefix(data_type)

            if is_struct_type(data_type):
                # struct implementation
                with self.output_to_relative_path(os.path.join(output_path, class_name + '.m')):
                    self.emit_raw(base)
                    self._generate_struct_class_m(data_type)

                # struct header
                with self.output_to_relative_path(os.path.join(output_path, class_name + '.h')):
                    self.emit_raw(base)
                    self._generate_struct_class_h(data_type)
            elif is_union_type(data_type):
                # union implementation
                with self.output_to_relative_path(os.path.join(output_path, class_name + '.m')):
                    self.emit_raw(base)
                    self._generate_union_class_m(data_type)

                # union header
                with self.output_to_relative_path(os.path.join(output_path, class_name + '.h')):
                    self.emit_raw(base)
                    self._generate_union_class_h(data_type)
            else:
                raise TypeError('Can\'t handle type %r' % type(data_type))

    def _generate_struct_class_m(self, struct):
        """Defines an Obj C implementation file that represents a struct in Stone."""
        self._generate_imports_m(self._get_imports_m(struct, default_imports=['DbxStoneSerializers',
                                                                              'DbxStoneValidators']))

        struct_name = fmt_class_prefix(struct)

        with self.block_m(struct_name):
            self._generate_struct_cstor(struct)
            self._generate_struct_cstor_default(struct)
            self._generate_serializable_funcs(struct_name)
            self._generate_description_func(struct_name)

        self.emit()
        self.emit()

        with self.block_m(fmt_serial_class(struct_name)):
            self._generate_struct_serializer(struct)
            self._generate_struct_deserializer(struct)

    def _generate_struct_class_h(self, struct):
        """Defines an Obj C header file that represents a struct in Stone."""
        self._generate_init_imports_h(struct)
        self._generate_imports_h(self._get_imports_h(struct, []))
        self._generate_class_comment(struct)

        struct_name = fmt_class_prefix(struct)

        with self.block_h_from_data_type(struct, protocol=['DbxSerializable']):
            self._generate_struct_properties(struct.fields)
            self._generate_struct_cstor_signature(struct)
            self._generate_struct_cstor_signature_default(struct)
            self._generate_serializable_signatures()
            self._generate_description_signature()

        self.emit()
        self.emit()

        with self.block_h(fmt_serial_class(struct_name)):
            self._generate_struct_serializer_signatures(struct_name)

    def _generate_union_class_m(self, union):
        """Defines an Obj C implementation file that represents a union in Stone."""
        self._generate_imports_m(self._get_imports_m(union, default_imports=['DbxStoneSerializers',
                                                                             'DbxStoneValidators']))

        union_name = fmt_class_prefix(union)

        with self.block_m(fmt_class_prefix(union)):
            self._generate_union_cstor_funcs(union)
            self._generate_union_tag_state_funcs(union)
            self._generate_union_tag_vars_funcs(union)
            self._generate_serializable_funcs(union_name)
            self._generate_description_func(union_name)

        self.emit()
        self.emit()

        with self.block_m(fmt_serial_class(union_name)):
            self._generate_union_serializer(union)
            self._generate_union_deserializer(union)

    def _generate_union_class_h(self, union):
        """Defines an Obj C header file that represents a union in Stone."""
        self._generate_init_imports_h(union)
        self._generate_imports_h(self._get_imports_h(union, []))
        self._generate_class_comment(union)

        union_name = fmt_class_prefix(union)

        with self.block_h_from_data_type(union, protocol=['DbxSerializable']):
            self._generate_union_tag_state(union)
            self._generate_union_cstor_signatures(union.all_fields)
            self._generate_union_tag_access_signatures(union)
            self._generate_serializable_signatures()
            self._generate_description_signature()
            self._generate_union_tag_property(union)
            self._generate_union_properties(union.all_fields)

        self.emit()
        self.emit()

        with self.block_h(fmt_serial_class(union_name)):
            self._generate_struct_serializer_signatures(union_name)

    def _generate_struct_cstor(self, struct):
        """Emits struct standard constructor."""
        with self.block_func(func=self._cstor_name_from_fields(struct.all_fields),
                             args=fmt_func_args_from_fields(struct.all_fields),
                             return_type='instancetype'):
            for field in struct.all_fields:
                self._generate_validator(field.data_type, fmt_var(field.name))

            self.emit()

            super_fields = [f for f in struct.all_fields if f not in struct.fields]

            if super_fields:
                super_args = fmt_func_args([(fmt_var(f.name), fmt_var(f.name)) for f in super_fields])
                self.emit('self = [super {}:{}];'.format(self._cstor_name_from_fields(super_fields),
                                                         super_args))
            else:
                self.emit('self = [super init];')
            with self.block_init():
                for field in struct.fields:
                    field_name = fmt_var(field.name)

                    if field.has_default:
                        self.emit('_{} = {} != nil ? {} : {};'.format(field_name,
                                                                      field_name,
                                                                      field_name,
                                                                      fmt_default_value(field)))
                    else:
                        self.emit('_{} = {};'.format(field_name, field_name))
        self.emit()

    def _generate_struct_cstor_default(self, struct):
        """Emits struct convenience constructor. Default arguments are omitted."""
        if not self._struct_has_defaults(struct):
            return

        fields_no_default = [f for f in struct.all_fields if not f.has_default]

        with self.block_func(func=self._cstor_name_from_fields(fields_no_default),
                             args=fmt_func_args_from_fields(fields_no_default),
                             return_type='instancetype'):
            cstor_args = fmt_func_args([(fmt_var(f.name), fmt_var(f.name)
                if not f.has_default else 'nil') for f in struct.all_fields])
            self.emit('return [self {}:{}];'.format(self._cstor_name_from_fields(struct.all_fields),
                                                    cstor_args))
        self.emit()

    def _generate_struct_cstor_signature(self, struct):
        """Emits struct standard constructor signature to be used in the struct's header file."""
        fields = struct.all_fields
        signature = fmt_signature(func=self._cstor_name_from_fields(fields),
                                  args=self._cstor_args_from_fields(fields, is_struct=True),
                                  return_type='nonnull instancetype')
        self.emit('{};'.format(signature))
        self.emit()

    def _generate_struct_cstor_signature_default(self, struct):
        """Emits struct convenience constructor with default arguments ommitted signature to be used in the
        struct header file."""
        if not self._struct_has_defaults(struct):
            return

        fields_no_default = [f for f in struct.all_fields if not f.has_default]
        signature = fmt_signature(func=self._cstor_name_from_fields(fields_no_default),
                                  args=self._cstor_args_from_fields(fields_no_default, is_struct=True),
                                  return_type='nonnull instancetype')
        self.emit('{};'.format(signature))
        self.emit()

    def _generate_union_cstor_funcs(self, union):
        """Emits standard union constructor."""
        union_name = fmt_class_prefix(union)
        enum_type = fmt_enum_name('tag', union)

        for field in union.all_fields:
            enum_field_name = fmt_enum_name(field.name, union)
            func_args = [] if is_void_type(field.data_type) else fmt_func_args_from_fields([field])

            with self.block_func(func=self._cstor_name_from_field(field),
                                 args=func_args,
                                 return_type='instancetype'):
                self.emit('self = [super init];')
                with self.block_init():
                    self.emit('_tag = ({}){};'.format(enum_type, enum_field_name))
                    if not is_void_type(field.data_type):
                        self.emit('_{} = {};'.format(fmt_var(field.name), fmt_var(field.name)))
            self.emit()

    def _generate_union_cstor_signatures(self, fields):
        """Emits union constructor signatures to be used in the union's header file."""
        for field in fields:
            args = self._cstor_args_from_fields([field] if not is_void_type(field.data_type) else [])
            signature = fmt_signature(func=self._cstor_name_from_field(field),
                                      args=args,
                                      return_type='nonnull instancetype')
            self.emit('{};'.format(signature))
            self.emit()

    def _generate_union_tag_state(self, union):
        """Emits union tag enum type, which stores union state."""
        union_name = fmt_class_prefix(union)

        with self.block('typedef NS_ENUM(NSInteger, {})'.format(fmt_enum_name('tag', union)),
                        after = ';'):
            for field in union.all_fields:
                doc = self.process_doc(field.doc, self._docf) if field.doc else undocumented
                self.emit_wrapped_text(doc, prefix=comment_prefix)
                self.emit('{},'.format(fmt_enum_name(field.name, union)))
        self.emit()

    def _generate_serializable_funcs(self, data_type_name):
        """Emits the two struct/union functions that implement the `Serializable` protocol."""
        with self.block_func(func='serialize',
                             args=fmt_func_args_declaration([('obj', 'id')]),
                             return_type='NSDictionary *',
                             class_func=True):
            self.emit('return {};'.format(fmt_func_call(caller=fmt_serial_class(data_type_name),
                                                        callee='serialize',
                                                        args=fmt_func_args([('obj', 'obj')]))))
        self.emit()

        with self.block_func(func='deserialize',
                             args=fmt_func_args_declaration([('dict', 'NSDictionary *')]),
                             return_type='id',
                             class_func=True):
            self.emit('return {};'.format(fmt_func_call(caller=fmt_serial_class(data_type_name),
                                                        callee='deserialize',
                                                        args=fmt_func_args([('dict', 'dict')]))))
        self.emit()

    def _generate_serializable_signatures(self):
        """Emits the signatures of the two struct/union functions that implement the `Serializable` protocol."""
        serial_signature = fmt_signature(func='serialize',
                                         args=fmt_func_args_declaration([('obj', 'id _Nonnull')]),
                                         return_type='NSDictionary * _Nonnull',
                                         class_func=True)
        deserial_signature = fmt_signature(func='deserialize',
                                           args=fmt_func_args_declaration([('dict', 'NSDictionary * _Nonnull')]),
                                           return_type='id _Nonnull',
                                           class_func=True)
        self.emit('{};'.format(serial_signature))
        self.emit()
        self.emit('{};'.format(deserial_signature))
        self.emit()

    def _generate_struct_serializer_signatures(self, struct_name):
        """Emits the signatures of the serializer object's serializing functions."""
        serial_signature = fmt_signature(func='serialize',
                                         args=fmt_func_args_declaration([('obj', '{} * _Nonnull'.format(struct_name))]),
                                         return_type='NSDictionary * _Nonnull',
                                         class_func=True)
        deserial_signature = fmt_signature(func='deserialize',
                                           args=fmt_func_args_declaration([('dict', 'NSDictionary * _Nonnull')]),
                                           return_type='{} * _Nonnull'.format(struct_name),
                                           class_func=True)
        self.emit('{};'.format(serial_signature))
        self.emit()
        self.emit('{};'.format(deserial_signature))
        self.emit()

    def _generate_description_signature(self):
        signature = fmt_signature(func='description',
                                  args=[],
                                  return_type='NSString * _Nonnull')
        self.emit('{};'.format(signature))
        self.emit()

    def _generate_description_func(self, data_type_name):
        with self.block_func(func='description',
                             args=[],
                             return_type='NSString *'):
            serialize_call = fmt_func_call(caller=fmt_serial_class(data_type_name),
                                           callee='serialize',
                                           args=fmt_func_args([('valueObj', 'self')]))
            self.emit('return {};'.format(fmt_func_call(caller=serialize_call,
                                                        callee='description')))
        self.emit()

    def _cstor_args_from_fields(self, fields, is_struct=False):
        """Returns a string representing the properly formatted arguments for a constructor."""
        if is_struct:
            args = [(fmt_var(f.name), fmt_type(f.data_type, tag=True, has_default=f.has_default)) for f in fields]
        else:
            args = [(fmt_var(f.name), fmt_type(f.data_type, tag=True)) for f in fields]

        return fmt_func_args_declaration(args)

    def _generate_validator(self, data_type, value):
        """Emits validator if data type has associated validator."""
        validator = self._determine_validator_type(data_type, value)

        if validator:
            self.emit('{}({});'.format(validator, value))

    def _determine_validator_type(self, data_type, value):
        """Returns validator string for given data type, else `None`."""
        data_type, nullable = unwrap_nullable(data_type)

        validator = None

        if is_list_type(data_type):
            item_validator = self._determine_validator_type(data_type.data_type, value)
            item_validator = item_validator if item_validator else 'nil'

            validator = '{}:{}'.format(
                fmt_validator(data_type),
                fmt_func_args([
                    ('minItems', '[NSNumber numberWithInt:{}]'.format(data_type.min_items)
                        if data_type.min_items else 'nil'),
                    ('maxItems', '[NSNumber numberWithInt:{}]'.format(data_type.max_items)
                        if data_type.max_items else 'nil'),
                    ('itemValidator', item_validator),
                ])
            )
        elif is_numeric_type(data_type):
            if data_type.min_value or data_type.max_value:
                validator = '{}:{}'.format(
                    fmt_validator(data_type),
                    fmt_func_args([
                        ('minValue', '[NSNumber numberWithInt:{}]'.format(data_type.min_value)
                            if data_type.min_value else 'nil'),
                        ('maxValue', '[NSNumber numberWithInt:{}]'.format(data_type.max_value)
                            if data_type.max_value else 'nil'),
                    ])
                )
        elif is_string_type(data_type):
            if data_type.pattern or data_type.min_length or data_type.max_length:
                pattern = data_type.pattern.encode(
                    'unicode_escape').replace("\"", "\\\"") if data_type.pattern else None
                validator = '{}:{}'.format(
                    fmt_validator(data_type),
                    fmt_func_args([
                        ('minLength', '[NSNumber numberWithInt:{}]'.format(
                            data_type.min_length) if data_type.min_length else 'nil'),
                        ('maxLength', '[NSNumber numberWithInt:{}]'.format(
                            data_type.max_length) if data_type.max_length else 'nil'),
                        ('pattern', '@"{}"'.format(pattern) if pattern else 'nil'),
                    ])
                )

        if validator:
            validator = fmt_func_call(caller='DbxStoneValidators',
                                      callee=validator)
            if nullable:
                validator = fmt_func_call(caller='DbxStoneValidators',
                                          callee='nullableValidator',
                                          args=validator)
        return validator

    def _generate_struct_serializer(self, struct):
        """Emits the serialize method for the serialization object for the given struct."""
        struct_name = fmt_class_prefix(struct)

        with self.block_func(func='serialize',
                             args=fmt_func_args_declaration([('valueObj', '{} *'.format(struct_name))]),
                             return_type='NSDictionary *',
                             class_func=True):
            self.emit('NSMutableDictionary *jsonDict = [[NSMutableDictionary alloc] init];')
            self.emit()

            for field in struct.all_fields:
                _, nullable = unwrap_nullable(field.data_type)

                input_value = 'valueObj.{}'.format(fmt_var(field.name))
                serialize_call = self._fmt_serialization_call(field.data_type, input_value, True)

                if not nullable:
                    self.emit('jsonDict[@"{}"] = {};'.format(field.name, serialize_call))
                else:
                    with self.block('if ({} != nil)'.format(input_value)):
                        self.emit('jsonDict[@"{}"] = {};'.format(field.name, serialize_call))
            self.emit()

            if struct.has_enumerated_subtypes():
                for tags, subtype in struct.get_all_subtypes_with_tags():
                    assert len(tags) == 1, tags
                    tag = tags[0]

                    with self.block('if ([valueObj isKindOfClass:[{} class]])'.format(fmt_class_prefix(subtype))):
                        serialize_call = fmt_func_call(caller=fmt_serial_class(fmt_class_prefix(subtype)),
                                                       callee='serialize',
                                                       args=fmt_func_args([('value', '({} *)valueObj'.format(fmt_class_prefix(subtype)))]))
                        self.emit('NSDictionary *subTypeFields = {};'.format(serialize_call))
                        with self.block('for (NSString* key in subTypeFields)'):
                            self.emit('jsonDict[key] = subTypeFields[key];')
                        self.emit('jsonDict[@".tag"] = @"{}";'.format(fmt_var(tag)))
                self.emit()
            self.emit('return jsonDict;')
        self.emit()

    def _generate_struct_deserializer(self, struct):
        """Emits the deserialize method for the serialization object for the given struct."""
        struct_name = fmt_class_prefix(struct)

        with self.block_func(func='deserialize',
                             args=fmt_func_args_declaration([('valueDict', 'NSDictionary *')]),
                             return_type='{} *'.format(struct_name),
                             class_func=True):            
            if not struct.has_enumerated_subtypes():
                for field in struct.all_fields:
                    _, nullable = unwrap_nullable(field.data_type)
                    input_value = 'valueDict[@"{}"]'.format(field.name)
                    deserialize_call = self._fmt_serialization_call(field.data_type, input_value, False)

                    if nullable:
                        deserialize_call = '{} != nil ? {} : nil'.format(input_value, deserialize_call)

                    self.emit('{}{} = {};'.format(fmt_type(field.data_type), fmt_var(field.name), deserialize_call))
                
                self.emit()

                deserialized_obj_args = [(fmt_var(f.name), fmt_var(f.name)) for f in struct.all_fields]
                init_call = fmt_func_call(caller=fmt_alloc_call(caller=struct_name),
                                          callee=self._cstor_name_from_fields(struct.all_fields),
                                          args=fmt_func_args(deserialized_obj_args))
                self.emit('return {};'.format(init_call))
            else:
                for tags, subtype in struct.get_all_subtypes_with_tags():
                    assert len(tags) == 1, tags
                    tag = tags[0]

                    with self.block('if ([valueDict[@".tag"] isEqualToString:@"{}"])'.format(fmt_var(tag))):
                        deserialize_call = fmt_func_call(caller=fmt_serial_class(fmt_class_prefix(subtype)),
                                                         callee='deserialize',
                                                         args=fmt_func_args([('value', 'valueDict')]))
                        self.emit('return {};'.format(deserialize_call))
                self.emit()
                self._generate_throw_error('InvalidTagEnum', 'Supplied tag enum has an invalid value.')
        
        self.emit()

    def _generate_union_serializer(self, union):
        """Emits the serialize method for the serialization object for the given union."""
        union_name = fmt_class_prefix(union)

        with self.block_func(func='serialize',
                             args=fmt_func_args_declaration([('valueObj', '{} *'.format(union_name))]),
                             return_type='NSDictionary *',
                             class_func=True):
            self.emit('NSMutableDictionary *jsonDict = [[NSMutableDictionary alloc] init];')
            self.emit()

            first_block = True
            for field in union.all_fields:
                with self.block('{} ([valueObj is{}])'.format('if' if first_block else 'else if',
                                                              fmt_camel_upper(field.name))):                    
                    data_type, nullable = unwrap_nullable(field.data_type)
                    input_value = 'valueObj.{}'.format(fmt_var(field.name))
                    serialize_call = self._fmt_serialization_call(field.data_type, input_value, True)

                    if not is_void_type(data_type):
                        if not nullable:
                            self.emit('jsonDict[@"{}"] = {};'.format(field.name, serialize_call))
                        else:
                            with self.block('if (![valueObj.{} isEqual:[NSNull null]])'.format(fmt_var(field.name))):
                                self.emit('jsonDict[@"{}"] = {};'.format(field.name, serialize_call))

                    self.emit('jsonDict[@".tag"] = @"{}";'.format(field.name))

                if first_block:
                    first_block = False

            with self.block('else'):                    
                self._generate_throw_error('InvalidTagEnum', 'Supplied tag enum has an invalid value.')

            self.emit()
            self.emit('return jsonDict;')

        self.emit()

    def _generate_union_deserializer(self, union):
        """Emits the deserialize method for the serialization object for the given union."""
        union_name = fmt_class_prefix(union)

        with self.block_func(func='deserialize',
                             args=fmt_func_args_declaration([('valueDict', 'NSDictionary *')]),
                             return_type='{} *'.format(union_name),
                             class_func=True):            
            self.emit('NSString *tag = valueDict[@".tag"];')
            self.emit()

            for field in union.all_fields:
                with self.block('if ([tag isEqualToString:@"{}"])'.format(field.name)):
                    if not is_void_type(field.data_type):
                        data_type, nullable = unwrap_nullable(field.data_type)
                        input_value = 'valueDict[@"{}"]'.format(field.name)
                        deserialize_call = self._fmt_serialization_call(field.data_type, input_value, False)

                        if nullable:
                            deserialize_call = '{} != nil ? {} : nil'.format(input_value, deserialize_call)

                        self.emit('{}{} = {};'.format(fmt_type(field.data_type),
                                                      fmt_var(field.name),
                                                      deserialize_call))
                        deserialized_obj_args = [(fmt_var(field.name), fmt_var(field.name))]
                    else:
                        deserialized_obj_args = []

                    self.emit('return {};'.format(fmt_func_call(caller=fmt_alloc_call(union_name),
                                                                callee=self._cstor_name_from_field(field),
                                                                args=fmt_func_args(deserialized_obj_args))))
            self.emit()
            self._generate_throw_error('InvalidTagEnum', 'Supplied tag enum has an invalid value.')
        self.emit()

    def _fmt_serialization_call(self, data_type, input_value, serialize):
        """Returns the appropriate serialization / deserialization method call for the given data type."""
        data_type, _ = unwrap_nullable(data_type)
        serializer_func = 'serialize' if serialize else 'deserialize'
        serializer_args = []

        if is_list_type(data_type):
            serializer_args.append(('value', input_value))
            serialization_call = self._fmt_serialization_call(data_type.data_type, 'obj', serialize)
            array_block = '^id(id obj) {{ return {}; }}'.format(serialization_call)
            serializer_args.append(('withBlock', array_block))
        elif is_timestamp_type(data_type):
            serializer_args.append(('value', input_value))
            serializer_args.append(('dateFormat', '@"{}"'.format(data_type.format)))
        else:
            serializer_args.append(('value', input_value))

        return '{}'.format(fmt_func_call(caller=fmt_serial_obj(data_type),
                                                 callee=serializer_func,
                                                 args=fmt_func_args(serializer_args)))

    def _generate_route_objects_m(self, route_schema, namespace):
        """Emits implementation files for `Route` objects which encapsulate information
        regarding each route. These objects are passed as parameters when route calls are made."""
        output_path = 'Routes/RouteObjects/{}.m'.format(fmt_route_obj_class(namespace.name))
        namespace_name = fmt_camel_upper(namespace.name)

        with self.output_to_relative_path(output_path):
            self.emit(comment_prefix)
            self.emit_wrapped_text('Stone Route Objects', prefix=comment_prefix)
            self.emit(comment_prefix)
            self.emit()

            import_data_types = self._get_namespace_route_imports(namespace)
            default_imports = ['{}'.format(fmt_routes_class(namespace.name)),
                'DbxStoneBase', '{}'.format(fmt_route_obj_class(namespace.name))]
            import_classes = self._get_imports_m(import_data_types, default_imports=default_imports)
            self._generate_imports_m(import_classes)

            with self.block_m(fmt_route_obj_class(namespace.name)):
                for route in namespace.routes:
                    route_name = fmt_route_var(namespace.name, route.name)
                    self.emit('static DbxRoute *{} = nil;'.format(route_name))
                self.emit()

                for route in namespace.routes:
                    route_name = fmt_route_var(namespace.name, route.name)
 
                    if route.deprecated:
                        deprecated = '@{}'.format('YES')
                    else:
                        deprecated = '@{}'.format('NO')

                    if not is_void_type(route.result_data_type):
                        result_type = fmt_func_call(caller=fmt_class_type(route.result_data_type),
                                                    callee='class')
                    else:
                        result_type = 'nil'

                    if not is_void_type(route.error_data_type):
                        error_type = fmt_func_call(caller=fmt_class_type(route.error_data_type),
                                                   callee='class')
                    else:
                        error_type = 'nil'

                    with self.block_func(func=route_name,
                                         args=[],
                                         return_type='DbxRoute *',
                                         class_func=True):
                        with self.block('if (!{})'.format(route_name)):
                            with self.block('{} = [[DbxRoute alloc] init:'.format(route_name),
                                            delim=(None, None),
                                            after='];'):
                                self.emit('@\"{}\"'.format(route.name))
                                self.emit('namespace_:@\"{}\"'.format(namespace.name))
                                self.emit('deprecated:{}'.format(deprecated))
                                self.emit('resultType:{}'.format(result_type))
                                self.emit('errorType: {}'.format(error_type))
                                
                                attrs = []
                                for field in route_schema.fields:
                                    attr_key = field.name
                                    attr_val = ("@\"{}\"".format(route.attrs.get(attr_key))
                                            if route.attrs.get(attr_key) else 'nil')
                                    attrs.append('@\"{}\": {}'.format(attr_key, attr_val))

                                self.generate_multiline_list(
                                    attrs, delim=('attrs: @{', '}'), compact=True)
                        self.emit('return {};'.format(route_name))
                    self.emit()

    def _generate_route_objects_h(self, route_schema, namespace):
        """Emits header files for `Route` objects which encapsulate information
        regarding each route. These objects are passed as parameters when route calls are made."""
        namespace_name = fmt_camel_upper(namespace.name)
        with self.output_to_relative_path('Routes/RouteObjects/{}.h'.format(fmt_route_obj_class(namespace.name))):
            self.emit(comment_prefix)
            self.emit_wrapped_text('Stone Route Objects', prefix=comment_prefix)
            self.emit(comment_prefix)
            self.emit()
            self.emit(fmt_import('DbxStoneBase'))
            self.emit()

            with self.block_h(fmt_route_obj_class(namespace.name)):
                for route in namespace.routes:
                    route_name = fmt_route_var(namespace.name, route.name)

                    route_obj_access_signature = fmt_signature(func=route_name,
                                                               args=None,
                                                               return_type='DbxRoute *',
                                                               class_func=True)
                    self.emit('{};'.format(route_obj_access_signature))
                    self.emit()

    def _generate_union_tag_access_signatures(self, union):
        """Emits the `is<TAG_NAME>` methods and `getTagName` method signatures for 
        determining tag state and retrieving human-readable value of tag state, respectively."""
        union_name = fmt_class_prefix(union)

        for field in union.all_fields:
            is_tag_signature = fmt_signature(func='is{}'.format(fmt_camel_upper(field.name)),
                                             args=[],
                                             return_type='BOOL')
            self.emit('{};'.format(is_tag_signature))
            self.emit()

        get_tag_name_signature = fmt_signature(func='getTagName',
                                               args=None,
                                               return_type='NSString * _Nonnull')
        self.emit('{};'.format(get_tag_name_signature))
        self.emit()

    def _generate_union_tag_state_funcs(self, union):
        """Emits the `is<TAG_NAME>` methods and `getTagName` method for determining
        tag state and retrieving human-readable value of tag state, respectively."""
        union_name = fmt_class_prefix(union)
        enum_type = fmt_enum_name('tag', union)

        for field in union.all_fields:
            enum_field_name = fmt_enum_name(field.name, union)

            with self.block_func(func='is{}'.format(fmt_camel_upper(field.name)),
                                 args=[],
                                 return_type='BOOL'):
                self.emit('return _tag == ({}){};'.format(enum_type, enum_field_name))
            self.emit()

        with self.block_func(func='getTagName',
                             args=[],
                             return_type='NSString *'):
            for field in union.all_fields:
                enum_field_name = fmt_enum_name(field.name, union)
                enum_full_value = '({}){}'.format(enum_type, enum_field_name)

                with self.block('if (_tag == {})'.format(enum_full_value)):
                    self.emit('return @"{}";'.format(enum_full_value))
            self.emit()
            self._generate_throw_error('InvalidTagEnum', 'Supplied tag enum has an invalid value.')
        self.emit()

    def _generate_union_tag_vars_funcs(self, union):
        """Emits the getter methods for retrieving tag-specific state. Setters throw
        an error in the event an associated tag state variable is accessed without
        the correct tag state."""
        union_name = fmt_class_prefix(union)
        enum_type = fmt_enum_name('tag', union)

        for field in union.all_fields:
            if not is_void_type(field.data_type):
                enum_field_name = fmt_enum_name(field.name, union)
                enum_full_value = '({}){}'.format(enum_type, enum_field_name)

                with self.block_func(func=fmt_camel(field.name),
                                     args=[],
                                     return_type=fmt_type(field.data_type)):

                    with self.block('if (_tag != {})'.format(enum_full_value),
                                    delim=('{','}')):
                        error_msg = 'Invalid tag: required {}, but was %@.'.format(enum_full_value)
                        throw_exc = '[NSException raise:@"IllegalStateException" format:@"{}", [self getTagName]];'
                        self.emit(throw_exc.format(error_msg))
                    self.emit('return _{};'.format(fmt_var(field.name)))
                self.emit()

    def _generate_struct_properties(self, fields):
        """Emits struct instance properties from the given fields."""
        for field in fields:
            doc = self.process_doc(field.doc, self._docf) if field.doc else undocumented
            self.emit_wrapped_text(self.process_doc(doc, self._docf), prefix=comment_prefix)
            self.emit(fmt_property(field=field))
 
        if fields:
            self.emit()

    def _generate_union_properties(self, fields):
        """Emits union instance properties from the given fields."""
        for field in fields:
            # void types do not need properties to store additional state information
            if not is_void_type(field.data_type):
                self.emit(fmt_property(field=field))

        if fields:
            self.emit()

    def _generate_union_tag_property(self, union):
        """Emits union instance property representing union state."""
        union_name = fmt_class_prefix(union)

        self.emit_wrapped_text('Current state of the {} union type.'.format(union_name),
            prefix=comment_prefix)
        self.emit(fmt_property_str(prop='tag',
                                   typ='{}'.format(fmt_enum_name('tag', union))))

    def _generate_class_comment(self, data_type):
        """Emits a generic class comment for a union or struct."""
        if is_struct_type(data_type):
            class_type = 'struct'
        elif is_union_type(data_type):
            class_type = 'union'
        else:
            raise TypeError('Can\'t handle type %r' % type(data_type))

        self.emit(comment_prefix)
        self.emit_wrapped_text('The {} {}.'.format(fmt_class_prefix(
            data_type), class_type),prefix=comment_prefix)
        if data_type.doc:
            self.emit(comment_prefix)
            self.emit_wrapped_text(self.process_doc(
                data_type.doc, self._docf),prefix=comment_prefix)
            self.emit(comment_prefix)
        else:
            self.emit(comment_prefix)

    def _generate_throw_error(self, name, reason):
        """Emits a generic error throwing line."""
        throw_exc = '@throw([NSException exceptionWithName:@"{}" reason:@"{}" userInfo:nil]);'
        self.emit(throw_exc.format(name, reason))
