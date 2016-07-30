from __future__ import absolute_import, division, print_function, unicode_literals

import argparse
import json
import os
import re

from contextlib import contextmanager

from stone.data_type import (
    is_list_type,
    is_struct_type,
    is_user_defined_type,
    is_union_type,
    is_void_type,
    unwrap_nullable,
)
from stone.target.obj_c_helpers import (
    fmt_alloc_call,
    fmt_camel,
    fmt_camel_upper,
    fmt_class,
    fmt_class_prefix,
    fmt_func,
    fmt_func_args,
    fmt_func_args_declaration,
    fmt_func_call,
    fmt_import,
    fmt_property_str,
    fmt_public_name,
    fmt_serial_obj,
    fmt_signature,
    fmt_type,
    fmt_var,
    is_primitive_type,
    is_ptr_type,
)
from stone.target.obj_c import (
    base,
    comment_prefix,
    ObjCBaseGenerator,
    stone_warning,
    undocumented,
)

_cmdline_parser = argparse.ArgumentParser(
    prog='ObjC-client-generator',
    description=(
        'Generates a ObjC class with an object for each namespace, and in each '
        'namespace object, a method for each route. This class assumes that the '
        'obj_c_types generator was used with the same output directory.'),
)
_cmdline_parser.add_argument(
    '-m',
    '--module-name',
    required=True,
    type=str,
    help=('The name of the ObjC module to generate. Please exclude the {.h,.m} '
          'file extension.'),
)
_cmdline_parser.add_argument(
    '-c',
    '--class-name',
    required=True,
    type=str,
    help=('The name of the ObjC class that contains an object for each namespace, '
          'and in each namespace object, a method for each route.')
)
_cmdline_parser.add_argument(
    '-t',
    '--transport-client-name',
    required=True,
    type=str,
    help='The name of the ObjC class that manages network API calls.',
)
_cmdline_parser.add_argument(
    '-y',
    '--client-args',
    required=True,
    type=str,
    help='The client-side route arguments to append to each route by style type.',
)
_cmdline_parser.add_argument(
    '-z'
    '--style-to-request',
    required=True,
    type=str,
    help='The dict that maps a style type to a ObjC request object name.',
)


class ObjCGenerator(ObjCBaseGenerator):
    """Generates ObjC client base that implements route interfaces."""
    cmdline_parser = _cmdline_parser

    def generate(self, api):
        for namespace in api.namespaces.values():
            ns_class = fmt_class(namespace.name)
            if namespace.routes:
                with self.output_to_relative_path('Routes/Dbx{}Routes.m'.format(ns_class)):
                    self._generate_routes_m(namespace)

                with self.output_to_relative_path('Routes/Dbx{}Routes.h'.format(ns_class)):
                    self._generate_routes_h(namespace)

        with self.output_to_relative_path('Client/{}.m'.format(self.args.module_name)):
            self._generate_client_m(api)

        with self.output_to_relative_path('Client/{}.h'.format(self.args.module_name)):
            self._generate_client_h(api)

    def _generate_client_m(self, api):
        """Generates client base implementation file. For each namespace, the client will
        have an object field that encapsulates each route in the particular namespace."""
        self.emit_raw(base)

        import_classes = ['Dbx{}Routes'.format(fmt_camel_upper(ns.name)) for ns in api.namespaces.values() if ns.routes]
        import_classes.append(self.args.transport_client_name)
        import_classes.append(self.args.module_name)
        self._generate_imports_m(import_classes)

        with self.block_m('{}'.format(self.args.class_name)):

            with self.block_func('init', fmt_func_args_declaration([('client', '{} *'.format(self.args.transport_client_name))]), return_type='instancetype'):
                self.emit('self = [super init];')

                with self.block_init():
                    for namespace in api.namespaces.values():
                        if namespace.routes:
                            self.emit('_{}Routes = [[Dbx{}Routes alloc] init: client];'.format(fmt_var(namespace.name), fmt_camel_upper(namespace.name)))

    def _generate_client_h(self, api):
        """Generates client base header file. For each namespace, the client will
        have an object field that encapsulates each route in the particular namespace."""
        self.emit_raw(base)
        self.emit('#import <Foundation/Foundation.h>')
        self.emit()

        import_classes = ['Dbx{}Routes'.format(fmt_camel_upper(ns.name)) for ns in api.namespaces.values() if ns.routes]
        import_classes.append(self.args.transport_client_name)
        self._generate_imports_h(import_classes)

        with self.block_h('{}'.format(self.args.class_name)):
            self.emit('{};'.format(fmt_signature('init', fmt_func_args_declaration([('client', '{} * _Nonnull'.format(self.args.transport_client_name))]), 'nonnull instancetype')))
            self.emit()

            for namespace in api.namespaces.values():
                if namespace.routes:
                    self.emit_wrapped_text('Routes within the {} namespace. See Dbx{}Routes for details.'.format(fmt_var(namespace.name), fmt_camel_upper(namespace.name)), prefix=comment_prefix)
                    self.emit(fmt_property_str('{}Routes'.format(fmt_var(namespace.name)), 'Dbx{}Routes * _Nonnull'.format(fmt_camel_upper(namespace.name))))

            self.emit()

    def _generate_routes_m(self, namespace):
        """Generates implementation file for namespace object that has as methods
        all routes within the namespace."""
        self.emit_raw(stone_warning)

        import_classes = ['Dbx{}Routes'.format(fmt_class(namespace.name))]
        import_classes.append(self.args.transport_client_name)
        import_classes.append('Dbx{}RouteObjects'.format(fmt_camel_upper(namespace.name)))
        import_classes.append('DbxStoneBase')
        import_classes += self._get_imports_m(self._get_namespace_route_imports(namespace), [])
        self._generate_imports_m(import_classes)

        with self.block_m('Dbx{}Routes'.format(fmt_camel_upper(namespace.name))):
            with self.block_func('init', fmt_func_args_declaration([('client', '{} *'.format(self.args.transport_client_name))]), return_type='instancetype'):
                self.emit('self = [super init];')
                with self.block_init():
                    self.emit('_client = client;')

            for route in namespace.routes:
                if is_struct_type(route.arg_data_type) and self._struct_has_defaults(route.arg_data_type):
                    arg_list, _ = self._get_default_route_args(namespace, route)
                    self._generate_route(route, namespace, arg_list)

                arg_list, _ = self._get_route_args(namespace, route)
                self._generate_route(route, namespace, arg_list)
    
    def _generate_route(self, route, namespace, arg_list):
        """Generates route method implementation for the given route."""
        route_arg_args_str = fmt_func_args_declaration(arg_list)
        cstor_name = self._cstor_name_from_fields_names(arg_list)

        result_type = '{} _Nullable'.format(fmt_type(route.result_data_type)) if not is_void_type(route.result_data_type) else ''
        arg_list.append(('success', 'void (^ _Nullable)({})'.format(result_type)))
        arg_list.append(('fail', 'void (^)(DropboxError *error)'))

        args_str = fmt_func_args_declaration(arg_list)

        with self.block_func(fmt_var(route.name), args_str):
            self.emit('DbxRoute *route = {}.dbx{};'.format('Dbx{}RouteObjects'.format(fmt_camel_upper(namespace.name)), '{}{}'.format(fmt_camel_upper(namespace.name), fmt_camel_upper(route.name))))
            if is_union_type(route.arg_data_type):
                self.emit('{} *arg = {};'.format(fmt_class_prefix(route.arg_data_type), fmt_var(route.arg_data_type.name)))
            elif not is_void_type(route.arg_data_type):
                self.emit('{} *arg = {};'.format(
                    fmt_class_prefix(route.arg_data_type), fmt_func_call(fmt_alloc_call(
                        fmt_class_prefix(route.arg_data_type)), cstor_name, route_arg_args_str)))

            self.emit('{};'.format(fmt_func_call('self.client', 'request', fmt_func_args([('route', 'route'), ('param', 'arg' if not is_void_type(route.arg_data_type) else 'nil'), ('success', 'success'), ('fail', 'fail')]))))             

        self.emit()

    def _generate_routes_h(self, namespace):
        """Generates header file for namespace object that has as methods
        all routes within the namespace."""
        self.emit_raw(stone_warning)

        import_classes = ['Dbx{}Routes'.format(fmt_class(namespace.name))]
        import_classes.append('DropboxError')
        import_classes.append(self.args.transport_client_name)
        import_classes += self._get_imports_m(self._get_namespace_route_imports(namespace), [])
        self._generate_imports_h(import_classes)

        self.emit_wrapped_text('Routes for the {} namespace'.format(fmt_class(namespace.name)), prefix=comment_prefix)

        with self.block_h('Dbx{}Routes'.format(fmt_class(namespace.name))):
            self.emit('{};'.format(fmt_signature('init', fmt_func_args_declaration([('client', '{} * _Nonnull'.format(self.args.transport_client_name))]), 'nonnull instancetype')))
            self.emit()

            for route in namespace.routes:
                if is_struct_type(route.arg_data_type) and self._struct_has_defaults(route.arg_data_type):
                    arg_list, doc_list = self._get_default_route_args(namespace, route)
                    self._generate_route_signature(route, namespace, arg_list, doc_list)

                arg_list, doc_list = self._get_route_args(namespace, route)
                self._generate_route_signature(route, namespace, arg_list, doc_list)

            self.emit(fmt_property_str('client', '{} * _Nonnull'.format(fmt_class(self.args.transport_client_name))))                    

    def _generate_route_signature(self, route, namespace, arg_list, doc_list):
        """Generates route method signature for the given route."""
        result_type = '{} _Nullable'.format(fmt_type(route.result_data_type)) if not is_void_type(route.result_data_type) else ''
        arg_list.append(('success', 'void (^ _Nullable)({})'.format(result_type)))
        arg_list.append(('fail', 'void (^ _Nullable)(DropboxError * _Nonnull error)'))

        deprecated = 'DEPRECATED: ' if route.deprecated else ''

        self.emit(comment_prefix)
        if route.doc:
            route_doc = self.process_doc(route.doc, self._docf)
        else:
            route_doc = 'The {} route'.format(func_name)
        self.emit_wrapped_text(deprecated + route_doc, prefix=comment_prefix, width=120)
        self.emit(comment_prefix)

        for name, doc in doc_list:
            self.emit_wrapped_text('- parameter {}: {}'.format(name, doc if doc else undocumented), prefix=comment_prefix, width=120)
        self.emit(comment_prefix)
        output = ('- returns: Through the response callback, the caller will ' +
                         'receive a `{}` object on success or a `{}` object on failure.')
        output = output.format(fmt_type(route.result_data_type, tag=True),
                               fmt_type(route.error_data_type, tag=True))
        self.emit_wrapped_text(output, prefix=comment_prefix, width=120)
        self.emit(comment_prefix)

        args_str = fmt_func_args_declaration(arg_list)

        deprecated = self._get_deprecation_warning(route)
        self.emit('{}{};'.format(fmt_signature(fmt_var(route.name), args_str, 'void'), deprecated))
        self.emit()

    def _get_deprecation_warning(self, route):
        result = ''
        if route.deprecated:
            msg = '{} is deprecated.'.format(route.name)
            if route.deprecated.by:
                msg += ' Use {}.'.format(route.deprecated.by.name)
            args = ["'{}'".format(msg), 'DeprecationWarning']
            result = ' __deprecated_msg("{}")'.format(msg)
        return result

    def _get_route_args(self, namespace, route):
        """Returns a list of name / value string pairs representing the arguments for
        a particular route."""
        data_type = route.arg_data_type
        arg_type = fmt_type(data_type, tag=True)
        if is_struct_type(data_type):
            arg_list = []
            for field in data_type.all_fields:
                unwrapped_data_type, nullable = unwrap_nullable(field.data_type)
                arg_list.append((fmt_var(field.name), fmt_type(unwrapped_data_type, tag=True, has_default=field.has_default)))
            
            doc_list = [(fmt_var(f.name), self.process_doc(f.doc, self._docf)) for f in data_type.fields if f.doc]
        elif is_union_type(data_type):
            arg_list = [(fmt_var(data_type.name), '{} * _Nonnull'.format(fmt_class_prefix(data_type)))]
            
            doc_list = [(fmt_var(data_type.name),
                self.process_doc(data_type.doc, self._docf)
                if data_type.doc else 'The {} union'.format(fmt_class(data_type.name)))]
        else:
            arg_list = [] if is_void_type(route.arg_data_type) else [('request', arg_type)]
            doc_list = []

        return arg_list, doc_list

    def _get_default_route_args(self, namespace, route):
        """Returns a list of name / value string pairs representing the default arguments for
        a particular route."""
        data_type = route.arg_data_type
        arg_type = fmt_type(data_type, tag=True)
        if is_struct_type(data_type):
            arg_list = []
            for field in data_type.all_fields:
                unwrapped_data_type, nullable = unwrap_nullable(field.data_type)
                if not field.has_default:
                    arg_list.append((fmt_var(field.name), fmt_type(unwrapped_data_type, tag=True)))

            doc_list = [(fmt_var(f.name), self.process_doc(f.doc, self._docf)) for f in data_type.fields if f.doc and not f.has_default]
        else:
            arg_list = []
            doc_list = []

        return arg_list, doc_list
