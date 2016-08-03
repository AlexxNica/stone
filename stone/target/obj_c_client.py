from __future__ import absolute_import, division, print_function, unicode_literals

import argparse
import json
import os
import re

from contextlib import contextmanager

from stone.data_type import (
    is_list_type,
    is_nullable_type,
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
    fmt_route_obj_class,
    fmt_route_var,
    fmt_routes_class,
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
            if namespace.routes:
                import_classes = [
                    fmt_routes_class(namespace.name),
                    fmt_route_obj_class(namespace.name),
                    self.args.transport_client_name,
                    'DbxStoneBase',
                    'DbxErrors',
                    'DbxTasks',
                ]

                with self.output_to_relative_path('Routes/{}.m'.format(fmt_routes_class(namespace.name))):
                    self.emit_raw(stone_warning)

                    imports_classes_m = import_classes + self._get_imports_m(self._get_namespace_route_imports(namespace), [])
                    self._generate_imports_m(imports_classes_m)

                    self._generate_routes_m(namespace)

                with self.output_to_relative_path('Routes/{}.h'.format(fmt_routes_class(namespace.name))):
                    self.emit_raw(base)
                    self.emit('#import <Foundation/Foundation.h>')
                    self.emit()

                    self._generate_imports_m(import_classes)
                    self.emit()
                    import_classes_h = self._get_imports_m(self._get_namespace_route_imports(namespace), [])
                    self._generate_imports_h(import_classes_h)

                    self._generate_routes_h(namespace)

        with self.output_to_relative_path('Client/{}.m'.format(self.args.module_name)):
            self._generate_client_m(api)

        with self.output_to_relative_path('Client/{}.h'.format(self.args.module_name)):
            self._generate_client_h(api)

    def _generate_client_m(self, api):
        """Generates client base implementation file. For each namespace, the client will
        have an object field that encapsulates each route in the particular namespace."""
        self.emit_raw(base)

        import_classes = [fmt_routes_class(ns.name) for ns in api.namespaces.values() if ns.routes]
        import_classes.append(self.args.transport_client_name)
        import_classes.append(self.args.module_name)
        self._generate_imports_m(import_classes)

        with self.block_m(self.args.class_name):
            client_args = fmt_func_args_declaration([('client', '{} *'.format(self.args.transport_client_name))])
            with self.block_func(func='init',
                                 args=client_args,
                                 return_type='instancetype'):
                self.emit('self = [super init];')

                with self.block_init():
                    for namespace in api.namespaces.values():
                        if namespace.routes:
                            self.emit('_{}Routes = [[{} alloc] init:client];'.format(fmt_var(namespace.name),
                                                                                     fmt_routes_class(namespace.name)))

    def _generate_client_h(self, api):
        """Generates client base header file. For each namespace, the client will
        have an object field that encapsulates each route in the particular namespace."""
        import_classes = [fmt_routes_class(ns.name) for ns in api.namespaces.values() if ns.routes]
        import_classes.append(self.args.transport_client_name)
        self._generate_imports_h(import_classes)

        with self.block_h(self.args.class_name):
            client_args = fmt_func_args_declaration([('client', '{} * _Nonnull'.format(self.args.transport_client_name))])
            init_signature = fmt_signature(func='init',
                                           args=client_args,
                                           return_type='nonnull instancetype')
            self.emit('{};'.format(init_signature))
            self.emit()

            for namespace in api.namespaces.values():
                if namespace.routes:
                    class_doc = 'Routes within the {} namespace. See {} for details.'.format(fmt_var(namespace.name),
                                                                                             fmt_routes_class(namespace.name))
                    self.emit_wrapped_text(class_doc, prefix=comment_prefix)
                    self.emit(fmt_property_str(prop='{}Routes'.format(fmt_var(namespace.name)),
                                               typ='{} * _Nonnull'.format(fmt_routes_class(namespace.name))))
            self.emit()

    def _generate_routes_m(self, namespace):
        """Generates implementation file for namespace object that has as methods
        all routes within the namespace."""
        with self.block_m(fmt_routes_class(namespace.name)):
            init_args = fmt_func_args_declaration([('client', '{} *'.format(self.args.transport_client_name))])

            with self.block_func(func='init',
                                 args=init_args,
                                 return_type='instancetype'):
                self.emit('self = [super init];')
                with self.block_init():
                    self.emit('_client = client;')

            for route in namespace.routes:
                route_type = route.attrs.get('style')
                client_args = json.loads(self.args.client_args)

                if route_type in client_args.keys():
                    for args_data in client_args[route_type]:
                        _, type_data_list = tuple(args_data)
                        extra_args = [tuple(type_data[:-1]) for type_data in type_data_list]

                        if is_struct_type(route.arg_data_type) and self._struct_has_defaults(route.arg_data_type):
                            route_args, _ = self._get_default_route_args(namespace, route)
                            self._generate_route_m(route, namespace, route_args, extra_args)

                        route_args, _ = self._get_route_args(namespace, route)
                        self._generate_route_m(route, namespace, route_args, extra_args)
                else:
                    if is_struct_type(route.arg_data_type) and self._struct_has_defaults(route.arg_data_type):
                        route_args, _ = self._get_default_route_args(namespace, route)
                        self._generate_route_m(route, namespace, route_args, [])

                    route_args, _ = self._get_route_args(namespace, route)
                    self._generate_route_m(route, namespace, route_args, [])
    
    def _generate_route_m(self, route, namespace, route_args, extra_args):
        """Generates route method implementation for the given route."""
        user_args = list(route_args)

        transport_args = [
            ('route', 'route'),
            ('arg', 'arg' if not is_void_type(route.arg_data_type) else 'nil'),
        ]

        for name, value, typ in extra_args:
            user_args.append((name, typ))
            transport_args.append((name, value))

        route_result_type = fmt_type(route.result_data_type, tag=False) if not is_void_type(route.result_data_type) else ''
        user_args.append(('success', 'void (^)({})'.format(route_result_type)))
        user_args.append(('fail', 'void (^)(DbxError *error)'))

        transport_args.append(('success', 'success'))
        transport_args.append(('fail', 'fail'))

        style_to_request = json.loads(self.args.z__style_to_request)
        route_task_type = '{} *'.format(style_to_request[route.attrs.get('style')])

        with self.block_func(func=fmt_var(route.name),
                             args=fmt_func_args_declaration(user_args),
                             return_type=route_task_type):
            self.emit('DbxRoute *route = {}.{};'.format(fmt_route_obj_class(namespace.name),
                                                        fmt_route_var(namespace.name, route.name)))
            if is_union_type(route.arg_data_type):
                self.emit('{} *arg = {};'.format(fmt_class_prefix(route.arg_data_type),
                                                 fmt_var(route.arg_data_type.name)))
            elif not is_void_type(route.arg_data_type):
                init_call = fmt_func_call(caller=fmt_alloc_call(caller=fmt_class_prefix(route.arg_data_type)),
                                          callee=self._cstor_name_from_fields_names(route_args),
                                          args=fmt_func_args_declaration(route_args))
                self.emit('{} *arg = {};'.format(fmt_class_prefix(route.arg_data_type),
                                                 init_call))
            request_call = fmt_func_call(caller='self.client',
                                         callee='request',
                                         args=fmt_func_args(transport_args))
            self.emit('return {};'.format(request_call))         
        self.emit()        

    def _generate_routes_h(self, namespace):
        """Generates header file for namespace object that has as methods
        all routes within the namespace."""
        self.emit_raw(stone_warning)

        self.emit_wrapped_text('Routes for the {} namespace'.format(fmt_class(namespace.name)),
                                                                    prefix=comment_prefix)

        with self.block_h(fmt_routes_class(namespace.name)):
            routes_obj_args = fmt_func_args_declaration(
                [('client', '{} * _Nonnull'.format(self.args.transport_client_name))])
            init_signature = fmt_signature(func='init',
                                           args=routes_obj_args,
                                           return_type='nonnull instancetype')
            self.emit('{};'.format(init_signature))
            self.emit()

            for route in namespace.routes:
                route_type = route.attrs.get('style')
                client_args = json.loads(self.args.client_args)

                if route_type in client_args.keys():
                    for args_data in client_args[route_type]:
                        _, type_data_list = tuple(args_data)
                        extra_args = [tuple(type_data[:-1]) for type_data in type_data_list]
                        extra_docs = [(type_data[0], type_data[-1]) for type_data in type_data_list]

                        if is_struct_type(route.arg_data_type) and self._struct_has_defaults(route.arg_data_type):
                            route_args, doc_list = self._get_default_route_args(namespace, route, tag=True)
                            self._generate_route_signature(route, namespace, route_args, extra_args, doc_list + extra_docs)

                        route_args, doc_list = self._get_route_args(namespace, route, tag=True)
                        self._generate_route_signature(route, namespace, route_args, extra_args, doc_list + extra_docs)
                else:
                    if is_struct_type(route.arg_data_type) and self._struct_has_defaults(route.arg_data_type):
                        route_args, doc_list = self._get_default_route_args(namespace, route, tag=True)
                        self._generate_route_signature(route, namespace, route_args, [], doc_list)

                    route_args, doc_list = self._get_route_args(namespace, route, tag=True)
                    self._generate_route_signature(route, namespace, route_args, [], doc_list)

            self.emit(fmt_property_str(prop='client',
                                       typ='{} * _Nonnull'.format(fmt_class(self.args.transport_client_name))))
            self.emit()

    def _generate_route_signature(self, route, namespace, route_args, extra_args, doc_list):
        """Generates route method signature for the given route."""
        for name, value, typ in extra_args:
            route_args.append((name, typ))

        result_type = '{} _Nullable'.format(
            fmt_type(route.result_data_type)) if not is_void_type(route.result_data_type) else ''
        route_args.append(('success', 'void (^ _Nullable)({})'.format(result_type)))
        route_args.append(('fail', 'void (^ _Nullable)(DbxError * _Nonnull error)'))

        style_to_request = json.loads(self.args.z__style_to_request)
        route_task_type = '{} *'.format(style_to_request[route.attrs.get('style')])

        deprecated = 'DEPRECATED: ' if route.deprecated else ''

        self.emit(comment_prefix)
        if route.doc:
            route_doc = self.process_doc(route.doc, self._docf)
        else:
            route_doc = 'The {} route'.format(func_name)
        self.emit_wrapped_text(deprecated + route_doc, prefix=comment_prefix, width=120)
        self.emit(comment_prefix)

        for name, doc in doc_list:
            self.emit_wrapped_text('- parameter {}: {}'.format(
                name, doc if doc else undocumented), prefix=comment_prefix, width=120)
        self.emit(comment_prefix)
        output = ('- returns: Through the response callback, the caller will ' +
                         'receive a `{}` object on success or a `{}` object on failure.')
        output = output.format(fmt_type(route.result_data_type, tag=True),
                               fmt_type(route.error_data_type, tag=True))
        self.emit_wrapped_text(output, prefix=comment_prefix, width=120)
        self.emit(comment_prefix)

        deprecated = self._get_deprecation_warning(route)
        route_signature = fmt_signature(func=fmt_var(route.name),
                                        args=fmt_func_args_declaration(route_args),
                                        return_type='{} _Nonnull'.format(route_task_type))
        self.emit('{}{};'.format(route_signature, deprecated))
        self.emit()

    def _get_deprecation_warning(self, route):
        """Returns a deprecation tag / message, if route is deprecated."""
        result = ''
        if route.deprecated:
            msg = '{} is deprecated.'.format(route.name)
            if route.deprecated.by:
                msg += ' Use {}.'.format(route.deprecated.by.name)
            result = ' __deprecated_msg("{}")'.format(msg)
        return result

    def _get_route_args(self, namespace, route, tag=False):
        """Returns a list of name / value string pairs representing the arguments for
        a particular route."""
        data_type, _ = unwrap_nullable(route.arg_data_type)
        if is_struct_type(data_type):
            arg_list = []
            for field in data_type.all_fields:
                arg_list.append((fmt_var(field.name), fmt_type(field.data_type, tag=True, has_default=field.has_default)))
            
            doc_list = [(fmt_var(f.name), self.process_doc(f.doc, self._docf)) for f in data_type.fields if f.doc]
        elif is_union_type(data_type):
            arg_list = [(fmt_var(data_type.name), fmt_type(route.arg_data_type, tag=tag))]
            
            doc_list = [(fmt_var(data_type.name),
                self.process_doc(data_type.doc, self._docf)
                if data_type.doc else 'The {} union'.format(fmt_class(data_type.name)))]
        else:
            arg_list = []
            doc_list = []

        return arg_list, doc_list

    def _get_default_route_args(self, namespace, route, tag=False):
        """Returns a list of name / value string pairs representing the default arguments for
        a particular route."""
        data_type, _ = unwrap_nullable(route.arg_data_type)
        if is_struct_type(data_type):
            arg_list = []
            for field in data_type.all_fields:
                if not field.has_default:
                    arg_list.append((fmt_var(field.name), fmt_type(field.data_type, tag=tag)))

            doc_list = [(fmt_var(f.name), self.process_doc(f.doc, self._docf))
                for f in data_type.fields if f.doc and not f.has_default]
        else:
            arg_list = []
            doc_list = []

        return arg_list, doc_list
