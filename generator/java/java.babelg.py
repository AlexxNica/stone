"""Generate Java classes from Babel specs.

See https://github.com/dropbox/babelapi
"""
# TODO: Support {".tag": <tag>, ".tag.<tag>" : "<subtag>", ...}.
# TODO: Don't generate assert statements, throw something.
# TODO: Don't throw XXX for "Don't know how to write/validate" cases.
# TODO: Should _reader not be public? Or should _writer be public?
# TODO: Namespace comments.

from __future__ import absolute_import, division, print_function, unicode_literals

import os

from babelapi.generator import CodeGenerator
from babelapi.data_type import (
    is_binary_type,
    is_boolean_type,
    is_composite_type,
    is_foreign_ref,
    is_numeric_type,
    is_nullable_type,
    is_list_type,
    is_string_type,
    is_struct_type,
    is_timestamp_type,
    is_union_type,
    is_void_type,
    TagRef,
    Union,
    Void,
)

# TODO: Add all Java reserved words.
reserved_words = {'if', 'while', 'continue', 'public'}


def _fixreserved(s):
    if s in reserved_words:
        s += '_'
    return s


def _capwords(s):
    words = s.replace('/', '_').split('_')
    return ''.join(w[:1].upper() + w[1:] for w in words)


def _camelcase(s):
    s = _capwords(s)
    return s[:1].lower() + s[1:]


def capwords(s):
    return _fixreserved(_capwords(s))


def camelcase(s):
    return _fixreserved(_camelcase(s))


def is_simple_field(field):
    return isinstance(field.data_type, Void)


def has_value_fields(data_type):
    assert is_union_type(data_type)
    for field in data_type.all_fields:
        if not is_simple_field(field):
            return True
    return False


def classname(s):
    return capwords(s)


def routename(s):
    return camelcase(s)


type_map = {
    'UInt64': 'Long',
    'Int64': 'Long',
    'UInt32': 'Long',
    'Int32': 'Integer',
    'Float64': 'Double',
    'Float32': 'Float',
    'Boolean': 'Boolean',
    'Binary': 'byte[]',
    'String': 'String',
    'Timestamp': 'java.util.Date',
    'Void': 'void',
}


def maptype(namespace, data_type):
    """Map a Babel data type to a Java type expression.

    There are special cases for primitive types, list (array) types,
    and struct/union types.
    """
    while is_nullable_type(data_type) or is_foreign_ref(data_type):
        data_type = data_type.data_type
    if is_list_type(data_type):
        return 'java.util.ArrayList<%s>' % maptype(namespace, data_type.data_type)
    if data_type.name in type_map:
        return type_map[data_type.name]
    assert is_composite_type(data_type), data_type
    return classname(data_type.name)
    return 'com.dropbox.%s.%s.%s' % (camelcase(namespace.name),
                                     classname(namespace.name),
                                     classname(data_type.name))


def mapreader(namespace, data_type):
    """Map a Babel data type to a Java expression giving a Reader instance.

    This is not quite the same as maptype(...) + '._reader' since
    there are exceptions for various types.

    The generated code assumes all classes from com.dropbox.core.json
    have been imported.
    """
    while is_nullable_type(data_type) or is_foreign_ref(data_type):
        data_type = data_type.data_type
    if is_list_type(data_type):
        return 'JsonArrayReader.mk(%s)' % mapreader(namespace, data_type.data_type)
    if is_composite_type(data_type):
        return maptype(namespace, data_type) + '._reader'
    if is_string_type(data_type):
        return 'JsonReader.StringReader'
    if is_boolean_type(data_type):
        return 'JsonReader.BooleanReader'
    if is_numeric_type(data_type):
        # Assume JsonReader defines <foo>Reader for every integer and float type.
        return 'JsonReader.%sReader' % data_type.name
    if is_timestamp_type(data_type):
        return 'JsonDateReader.Dropbox'
    if is_binary_type(data_type):
        return 'JsonReader.BinaryReader'
    if is_void_type(data_type):
        return 'JsonReader.VoidReader'
    assert False, data_type  # Unsupported primitive type


def mapvalue(namespace, data_type, value):
    """Map a Babel (Python) value to a Java expression."""
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, float):
        return repr(value)  # Because str() drops the last few digits.
    if data_type.name in ('Int64', 'UInt64', 'UInt32'):
        return str(value) + 'L'  # Need exact type match for boxed values.
    if isinstance(data_type, Union):
        assert isinstance(value, TagRef), (data_type, value)
        assert data_type is value.union_data_type, (data_type, value)
        return '%s.%s' % (maptype(namespace, data_type), value.tag_name)
    return str(value)


# Matcher for Babel doc references.
docref = ':(?P<tag>[A-z]*):`(?P<val>.*?)`'


def doc_ref_handler(tag, val, route_formatter):
    """Substitute references in Babel docstrings with the proper Javadoc format."""
    if tag == 'route':
        return '{@link #%s}' % route_formatter(val)
    elif tag == 'type':
        return '{@link %s}' % classname(val)
    elif tag == 'field':
        return '{@code %s}' % camelcase(val)
    elif tag == 'link':
        anchor, link = val.rsplit(' ', 1)
        return '<a href="%s">%s</a>' % (link, anchor)
    elif tag == 'val':
        # Note that all valid Babel literals happen to be valid Java literals.
        return '{@literal %s}' % val
    else:
        assert False, 'Unsupported tag (:%s:`%s`)' % (tag, val)


def get_ancestors(data_type):
    """Return list of (tag, data_type) pairs.

    The first pair is the root and always has tag None.
    The last pair represents the argument.

    The tag is only present if the data_type in that pair has an
    ancestor and is a member of that ancestore's enumerated subtypes.

    Suppose we have the following tree:

      struct A
      struct B extends A
      struct C extends C

    Without enumerated subtypes:
    - get_ancestors(C) returns [(None, A), (None, B), (None, C)]
    - get_ancestors(B) returns [(None, A), (None, B)]
    - get_ancestors(A) returns [(None, A)]

    Now add enumerated subtypes, so the tree becomes:

    struct A
      union
        b B
    struct B extends A
      union
        c C
    struct C extends B

    Now the return values are:
    - get_ancestors(C) returns [(None, A), ('b', B), ('c', C)]
    - get_ancestors(B) returns [(None, A), ('b', B)]
    - get_ancestors(A) returns [(None, A)]
    """
    ancestors = []
    while data_type is not None:
        parent_type = data_type.parent_type
        tag = None
        if parent_type is not None and parent_type.has_enumerated_subtypes():
            for field in parent_type.get_enumerated_subtypes():
                if field.data_type is data_type:
                    tag = field.name
                    break
            else:
                assert False, "Type %s not found in subtypes of ancestor %s" % (data_type.name,
                                                                                parent_type.name)
        ancestors.append((tag, data_type))
        data_type = parent_type
    ancestors.reverse()
    return ancestors


class JavaCodeGenerator(CodeGenerator):

    def bsemi(self, before=''):
        """Like self.block(), but with a semicolon after the closing brace."""
        return self.block(before, after=';')

    def generate(self, api):
        """Toplevel code generation method.

        This is called by babelapi.cli.
        """
        # Create a package for each namespace containing datatypes and routes.
        for namespace in api.namespaces.values():
            package_components = ['com', 'dropbox', camelcase(namespace.name)]
            package_name = '.'.join(package_components)
            package_relpath = os.path.join(*package_components)
            package_fullpath = os.path.join(self.target_folder_path, package_relpath)
            if not os.path.isdir(package_fullpath):
                self.logger.info('Creating directory %s', package_fullpath)
                os.makedirs(package_fullpath)

            # Create a <Namespace>.java file containing nested classes.
            self.generate_namespace_wrapper(namespace, package_relpath, package_name)

    def generate_namespace_wrapper(self, namespace, package_relpath, package_name):
        out = self.emit
        class_name = classname(namespace.name)
        file_name = os.path.join(package_relpath, class_name + '.java')
        with self.output_to_relative_path(file_name):
            out('/* DO NOT EDIT */')
            out('/* This file was generated from %s.babel */' % namespace.name)
            out('')
            out('package %s;' % package_name)
            out('')
            out('import java.io.IOException;')
            out('import java.util.regex.Pattern;')
            out('import com.fasterxml.jackson.core.JsonGenerator;')
            out('import com.fasterxml.jackson.core.JsonParser;')
            out('import com.fasterxml.jackson.core.JsonToken;')
            out('import com.dropbox.core.DbxApiError;')
            out('import com.dropbox.core.DbxClient;')
            out('import com.dropbox.core.DbxException;')
            out('import com.dropbox.core.DbxRequestUtil;')
            out('import com.dropbox.core.http.HttpRequestor;')
            out('import com.dropbox.core.json.JsonArrayReader;')
            out('import com.dropbox.core.json.JsonDateReader;')
            out('import com.dropbox.core.json.JsonReader;')
            out('import com.dropbox.core.json.JsonReadException;')
            out('import com.dropbox.core.json.JsonWriter;')

            namespace_data_types = sorted(namespace.distinct_route_io_data_types(),
                                          key=lambda dt: dt.name)
            if namespace_data_types:
                to_import = []
                for data_type in namespace_data_types:
                    if is_foreign_ref(data_type):
                        dt_name = data_type.name.split('.')[-1]
                        to_import.append((data_type.namespace_name, dt_name))
                if to_import:
                    out('')
                    for ns_name, dt_name in to_import:
                        out('import com.dropbox.%s.%s.%s;' %
                            (ns_name, classname(ns_name), classname(dt_name)))

            out('')
            self.generate_doc('Classes and routes in namespace "%s".' % namespace.name)
            with self.block('public final class %s' % class_name):
                out('// namespace %s' % namespace.name)
                out('')
                out('private final DbxClient client;')
                out('')
                with self.block('public %s(DbxClient client)' % class_name):
                    out('this.client = client;')
                for data_type in namespace.linearize_data_types():
                    out('')
                    self.generate_data_type_class(namespace, data_type)
                for route in namespace.routes:
                    self.generate_route_stuff(namespace, route)

    def generate_route_stuff(self, namespace, route):
        out = self.emit
        arg_name = maptype(namespace, route.request_data_type)
        result_name = maptype(namespace, route.response_data_type)
        error_name = maptype(namespace, route.error_data_type)
        method_name = camelcase(route.name)
        exc_name = classname(route.name + '_exception')
        result_reader = mapreader(namespace, route.response_data_type)
        error_reader = mapreader(namespace, route.error_data_type)
        out('')
        self.generate_doc('Exception thrown by {@link #%s}.' % method_name)
        with self.block('public static class %s extends DbxApiError' % exc_name):
            if error_name == 'void':
                with self.block('public %s()' % exc_name):
                    out('super("Exception in %s");' % route.name)
            else:
                self.generate_doc('The error reported by %s.' % method_name)
                out('public final %s errorValue;' % error_name)
                out('')
                with self.block('public %s(%s errorValue)' % (exc_name, error_name)):
                    out('super("Exception in %s: " + errorValue);' % route.name)
                    out('this.errorValue = errorValue;')
        style = route.attrs.get('style', 'rpc')
        if style == 'upload':
            error_maker = camelcase(route.name + '_error_maker')
            uploader_maker = camelcase(route.name + '_uploader_maker')
            out('static DbxRequestUtil.RouteSpecificErrorMaker<%s> %s = '
                'new DbxRequestUtil.RouteSpecificErrorMaker<%s>()' %
                (exc_name, error_maker, exc_name))
            with self.bsemi():
                out('@Override')
                with self.block('public %s makeError(DbxRequestUtil.ErrorWrapper ew)' % exc_name):
                    if error_name == 'void':
                        out('return new %s();' % exc_name)
                    else:
                        out('return new %s((%s) (ew.errValue));' % (exc_name, error_name))
            resname = 'Object' if result_name == 'void' else result_name
            errname = 'Object' if error_name == 'void' else error_name
            self.generate_doc(
                'The {@link com.dropbox.core.DbxUploader} returned by {@link #%s}.' % method_name)
            uploader = classname(route.name + '_uploader')
            with self.block('public static class %s '
                            'extends com.dropbox.core.DbxUploader<%s,%s,%s>' %
                            (uploader, resname, errname, exc_name)):
                with self.block('%s(HttpRequestor.Uploader httpUploader, '
                                'JsonReader<%s> resultReader, JsonReader<%s>errorReader, '
                                'DbxRequestUtil.RouteSpecificErrorMaker<%s> errorMaker)'
                                % (uploader, resname, errname, exc_name)):
                    out('super(httpUploader, resultReader, errorReader, errorMaker);')
            out('static com.dropbox.core.DbxUploader.UploaderMaker'
                '<%s,%s,%s> %s = '
                'new com.dropbox.core.DbxUploader.UploaderMaker<%s,%s,%s>()' %
                (resname, errname, exc_name, uploader_maker, resname, errname, exc_name))
            with self.bsemi():
                out('@Override')
                with self.block('public com.dropbox.core.DbxUploader<%s,%s,%s> '
                                'makeUploader(HttpRequestor.Uploader httpUploader)' %
                                (resname, errname, exc_name)):
                    out('return new %s'
                        '(httpUploader, %s, %s, %s);' %
                        (uploader, result_reader, error_reader, error_maker))
            self.generate_doc(route.doc)
            if arg_name == 'void':
                out('public %s %s()' % (uploader, method_name))
            else:
                out('public %s %s(%s arg)' % (uploader, method_name, arg_name))
            out('        throws DbxException')
        elif style == 'download':
            self.generate_doc(route.doc)
            if arg_name == 'void':
                out('public com.dropbox.core.DbxDownloader<%s>'
                    ' %s()' % (result_name, method_name))
            else:
                out('public com.dropbox.core.DbxDownloader<%s>'
                    ' %s(%s arg)' %
                    (result_name, method_name, arg_name))
            out('        throws %s, DbxException' % exc_name)
        else:
            self.generate_doc(route.doc)
            if arg_name == 'void':
                out('public %s %s()' % (result_name, method_name))
            else:
                out('public %s %s(%s arg)' %
                    (result_name, method_name, arg_name))
            out('        throws %s, DbxException' % exc_name)
        with self.block():
            if arg_name != 'void':
                out('%s._reader.validate(arg);' % arg_name)  # Fails if arg isn't a struct or union.
            with self.block('try'):
                host = route.attrs.get('host', 'api')
                if style == 'upload':
                    self.generate_multiline_list([
                        'client.getRequestConfig()',
                        'client.getAccessToken()',
                        'client.getHost().%s' % host,
                        '"2-beta-2/%s/%s"' % (namespace.name, route.name),
                        'arg' if arg_name != 'void' else 'null',
                        arg_name + '._writer' if arg_name != 'void' else 'null',
                        uploader_maker,
                    ], before='return (%s) DbxRequestUtil.uploadStyle' % uploader, after=';')
                else:
                    ret = '' if is_void_type(route.response_data_type) else 'return '
                    self.generate_multiline_list([
                        'client.getRequestConfig()',
                        'client.getAccessToken()',
                        'client.getHost().%s' % host,
                        '"2-beta-2/%s/%s"' % (namespace.name, route.name),
                        'arg' if arg_name != 'void' else 'null',
                        arg_name + '._writer' if arg_name != 'void' else 'null',
                        '%s' % result_reader,
                        '%s' % error_reader,
                    ], before='%sDbxRequestUtil.%sStyle' % (ret, style), after=';')
            if style != 'upload':
                with self.block('catch (DbxRequestUtil.ErrorWrapper ew)'):
                    if error_name == 'void':
                        out('throw new %s();' % exc_name)
                    else:
                        out('throw new %s((%s) (ew.errValue));' % (exc_name, error_name))
            else:
                # TODO: The right way to do this is not to
                # emit the try{} wrapper if it's not rpc style.
                out('catch (DbxException ex) { throw ex; } // Dummy')
        if is_struct_type(route.request_data_type):
            # Generate a shortcut with unpacked args.
            self.generate_doc(route.doc)
            if style == 'upload':
                rtype = uploader
                ret = 'return '
            elif style == 'download':
                rtype = 'com.dropbox.core.DbxDownloader<%s>' % result_name
                ret = 'return '
            else:
                rtype = result_name
                ret = '' if rtype == 'void' else 'return '
            args = ['%s %s' % (maptype(namespace, field.data_type), camelcase(field.name))
                    for field in route.request_data_type.all_fields]
            out('public %s %s(%s)' % (rtype, method_name, ', '.join(args)))
            out('      throws %s, DbxException' % exc_name)
            with self.block():
                out('%s arg = new %s();' % (arg_name, arg_name))
                for field in route.request_data_type.all_fields:
                    fn = camelcase(field.name)
                    out('arg.%s = %s;' % (fn, fn))
                out('%s%s(arg);' % (ret, method_name))

    def generate_data_type_class(self, namespace, data_type):
        """Generate a class definition for a datatype (a struct or a union)."""
        out = self.emit
        class_name = classname(data_type.name)
        self.generate_doc(data_type.doc)
        if is_union_type(data_type):
            if has_value_fields(data_type):
                self.generate_union_complex(namespace, data_type, class_name)
            else:
                self.generate_union_simple(namespace, data_type, class_name)
        else:
            # Struct.
            assert is_struct_type(data_type)
            decl = 'public static class %s' % class_name
            if data_type.parent_type:
                decl += ' extends %s ' % classname(data_type.parent_type.name)
            with self.block(decl):
                out('// struct %s' % class_name)
                # Generate fields declarations.
                for field in data_type.fields:
                    self.generate_doc(field.doc)
                    out('public %s %s;' %
                        (maptype(namespace, field.data_type), camelcase(field.name)))
                out('')

                # Generate JSON writer for struct.
                self.generate_json_writer(namespace, class_name, data_type)
                out('')

                # Generate JSON reader for struct.
                self.generate_json_reader(namespace, class_name, data_type)
                out('')

                # Generate toString(), toStringMultiline(), toJson(), fromJson() methods.
                with self.block('public String toString()'):
                    out('return "%s." + _writer.writeToString(this, false);' % class_name)
                with self.block('public String toStringMultiline()'):
                    out('return "%s." + _writer.writeToString(this, true);' % class_name)
                with self.block('public String toJson(Boolean longForm)'):
                    out('return _writer.writeToString(this, longForm);')
                out('public static %s fromJson(String s)' % class_name)
                out('    throws JsonReadException')
                with self.block():
                    out('return _reader.readFully(s);')

    def generate_union_simple(self, namespace, data_type, class_name):
        """Generate code for a simple union (one that has only Void values)."""
        out = self.emit
        with self.block('public enum %s' % class_name):
            out('// union %s' % class_name)
            self.generate_enum_values(data_type, do_doc=True)
            out('')

            # Generate JSON writer.
            out('static final JsonWriter<%s> _writer = new JsonWriter<%s>()' %
                (class_name, class_name))
            with self.bsemi():
                out('public void write(%s x, JsonGenerator g)' % class_name)
                out(' throws IOException')
                with self.block():
                    with self.block('switch (x)'):
                        for field in data_type.all_fields:
                            out('case %s:' % camelcase(field.name))
                            with self.indent():
                                out('g.writeStartObject();')
                                out('g.writeFieldName(".tag");')
                                out('g.writeString("%s");' % field.name)
                                out('g.writeEndObject();')
                                out('break;')
            out('')

            # Generate JSON reader.
            out('public static final JsonReader<%s> _reader = '
                'new JsonReader<%s>()' % (class_name, class_name))
            with self.bsemi():
                out('public final %s read(JsonParser parser)' % class_name)
                out('    throws IOException, JsonReadException')
                with self.block():
                    catch_all = 'null'
                    if data_type.catch_all_field is not None:
                        catch_all = camelcase(data_type.catch_all_field.name)
                    out('return JsonReader.readEnum(parser, _values, %s);' % catch_all)

            self.generate_static_values(data_type, class_name)
            out('')

            # Generate toJson() and fromJson() methods.
            with self.block('public String toJson(Boolean longForm)'):
                out('return _writer.writeToString(this, longForm);')
            out('public static %s fromJson(String s)' % class_name)
            out('    throws JsonReadException')
            with self.block():
                out('return _reader.readFully(s);')

    def generate_union_complex(self, namespace, data_type, class_name):
        """Generate code for a complex union (one that has at least one non-Void value)."""
        out = self.emit
        out('')
        with self.block('public static final class %s' % class_name):
            out('// union %s' % class_name)
            out('')
            # Generate a public enum named Tag.
            self.generate_doc('The discriminating tag type for {@link %s}.' % class_name)
            tag_name = 'Tag'
            with self.block('public enum %s' % tag_name):
                self.generate_enum_values(data_type, last_sep='')
            out('')
            # Generate a public field holding the tag.
            self.generate_doc('The discriminating tag for this instance.')
            out('public final %s tag;' % tag_name)
            out('')
            # Generate a private constructor to set the tag.
            with self.block('private %s(%s t)' % (class_name, tag_name)):
                out('tag = t;')
            # Generate stuff for each field:
            # - for simple fields, a public static final instance;
            # - for complex fields, a bunch of methods.
            unique_value_types = {}  # Map type name -> value name
            for field in data_type.all_fields:
                out('')
                field_name = camelcase(field.name)
                if is_simple_field(field):
                    self.generate_doc(field.doc)
                    out('public static final %s %s = new %s(%s.%s);' %
                        (class_name, field_name, class_name, tag_name, field_name))
                else:
                    # For fields with values, define:
                    # - a private member to hold the value(*);
                    # - a private constructor(*);
                    # - a public factory method;
                    # - a public getter method for the value.
                    # (*) Suppressed (shared) if a previous field uses the same type.
                    type_name = maptype(namespace, field.data_type)
                    if type_name not in unique_value_types:
                        value_name = camelcase(field.name + '_value')
                        unique_value_types[type_name] = value_name
                        out('private %s %s;' % (type_name, value_name))
                        with self.block('private %s(%s t, %s v)' %
                                        (class_name, tag_name, type_name)):
                            out('tag = t;')
                            out('%s = v;' % value_name)
                    else:
                        value_name = unique_value_types[type_name]
                        out('// Reusing %s for %s' % (value_name, camelcase(field_name)))
                    self.generate_doc(field.doc)
                    with self.block('public static %s %s(%s v)' %
                                    (class_name, field_name, type_name)):
                        if not is_nullable_type(field.data_type):
                            with self.block('if (v == null)'):
                                out('throw new RuntimeException'
                                    '("value for \'%s\' must not be null");' %
                                    field_name)
                        out('return new %s(%s.%s, v);' % (class_name, tag_name, field_name))
                    getter_name = camelcase('get_' + field.name)
                    with self.block('public %s %s()' % (type_name, getter_name)):
                        with self.block('if (tag != %s.%s)' % (tag_name, field_name)):
                            out('throw new RuntimeException'
                                '("%s() requires tag==%s, actual tag=="+tag);' %
                                (getter_name, field_name))
                        out('return %s;' % value_name)
            out('')

            # Generate JSON writer.
            out('static final JsonWriter<%s> _writer = new JsonWriter<%s>()' %
                (class_name, class_name))
            with self.bsemi():
                out('public final void write(%s x, JsonGenerator g)' % class_name)
                out('  throws IOException')
                with self.block():
                    with self.block('switch (x.tag)'):
                        for field in data_type.all_fields:
                            out('case %s:' % camelcase(field.name))
                            with self.indent():
                                tn = maptype(namespace, field.data_type)
                                out('g.writeStartObject();')
                                out('g.writeFieldName(".tag");')
                                out('g.writeString("%s");' % field.name)
                                if not is_simple_field(field):
                                    vn = 'x.' + unique_value_types[tn]

                                    def doit(dt):
                                        if (is_struct_type(dt) and
                                                not dt.has_enumerated_subtypes()):
                                            # Collapse struct into union.
                                            out('%s._writer.writeFields(%s, g);' % (
                                                classname(dt.name), vn))
                                        else:
                                            self.generate_write_field(namespace, field, vn)

                                    if is_nullable_type(field.data_type):
                                        with self.block('if (%s != null)' % vn):
                                            doit(field.data_type.data_type)
                                    else:
                                        doit(field.data_type)
                                out('g.writeEndObject();')
                                out('break;')
            out('')

            # Generate JSON reader.
            out('public static final JsonReader<%s> _reader = new JsonReader<%s>()' %
                (class_name, class_name))
            with self.bsemi():
                out('public final %s read(JsonParser parser)' % class_name)
                out('  throws IOException, JsonReadException')
                with self.block():
                    with self.block('if (parser.getCurrentToken() == JsonToken.VALUE_STRING)'):
                        out('String text = parser.getText();')
                        out('parser.nextToken();')
                        out('%s tag = _values.get(text);' % tag_name)
                        if data_type.catch_all_field is not None:
                            out('if (tag == null) { return %s.%s; }' %
                                (class_name, camelcase(data_type.catch_all_field.name)))
                        else:
                            with self.block('if (tag == null)'):
                                out('throw new JsonReadException'
                                    '("Unanticipated tag " + text + " without catch-all", '
                                    'parser.getTokenLocation());')
                        with self.block('switch (tag)'):
                            for field in data_type.all_fields:
                                if is_simple_field(field):
                                    out('case %s: return %s.%s;' %
                                        (camelcase(field.name), class_name, camelcase(field.name)))
                                elif is_nullable_type(field.data_type):
                                    out('case %s: return %s.%s(null);' %
                                        (camelcase(field.name), class_name, camelcase(field.name)))
                        out('throw new JsonReadException("Tag " + tag + " requires a value", '
                            'parser.getTokenLocation());')
                    # Else expect either {".tag": <tag>} or {".tag": <tag>, <tag>: <value>}.
                    out('JsonReader.expectObjectStart(parser);')
                    out('String[] tags = readTags(parser);')
                    out('assert tags != null && tags.length == 1;')
                    out('String text = tags[0];')
                    out('%s tag = _values.get(text);' % tag_name)
                    out('%s value = null;' % class_name)
                    with self.block('if (tag != null)'):
                        with self.block('switch (tag)'):
                            for field in data_type.all_fields:
                                fn = camelcase(field.name)
                                with self.block('case %s:' % fn):
                                    if is_simple_field(field):
                                        out('value = %s.%s;' % (class_name, fn))
                                        # Expect nothing more.
                                    else:
                                        dt = field.data_type
                                        if is_nullable_type(dt):
                                            with self.block('if (parser.getCurrentToken() == '
                                                            'JsonToken.END_OBJECT)'):
                                                out('break;')  # Null value is OK.
                                            dt = dt.data_type
                                        out('%s v = null;' % maptype(namespace, dt))
                                        if is_struct_type(dt) and not dt.has_enumerated_subtypes():
                                            # Collapse struct into union.
                                            out('v = %s._reader.readFields(parser);' %
                                                maptype(namespace, dt))
                                        else:
                                            out('assert parser.getCurrentToken() == '
                                                'JsonToken.FIELD_NAME;')
                                            out('text = parser.getText();')
                                            out('assert tags[0].equals(text);')
                                            out('parser.nextToken();')
                                            # TODO: generate_read_field() writes code using
                                            # readField() methods, which check for duplicate
                                            # fields. We can't have duplicate fields here, so
                                            # that code is useless.  Need to refactor
                                            # generate_read_field() more.
                                            self.generate_read_field(namespace, field, 'v')
                                        out('value = %s.%s(v);' % (class_name, fn))
                                    out('break;')
                    if data_type.catch_all_field is None:
                        with self.block('if (value == null)'):
                            out('throw new JsonReadException'
                                '("Unanticipated tag " + text, parser.getTokenLocation());')
                    out('JsonReader.expectObjectEnd(parser);')
                    if data_type.catch_all_field is not None:
                        out('if (value == null) { return %s.%s; }' %
                            (class_name, camelcase(data_type.catch_all_field.name)))
                    out('return value;')
                out('')

                # Generate validate() method.
                with self.block('public final void validate(%s value)' % class_name):
                    with self.block('switch (value.tag)'):
                        # A single no-op case for all simple fields.
                        cases = 0
                        for field in data_type.all_fields:
                            if is_simple_field(field):
                                out('case %s:' % camelcase(field.name))
                                cases += 1
                        if cases:
                            with self.indent():
                                out('break;')
                        # A separate case for each complex field.
                        for field in data_type.all_fields:
                            if not is_simple_field(field):
                                tn = maptype(namespace, field.data_type)
                                vn = 'value.' + unique_value_types[tn]
                                out('case %s:' % camelcase(field.name))
                                with self.indent():
                                    # TODO: Union fields may be optional but can't have defaults.
                                    # Also, required union fields are already checked for null-ness
                                    # when they are constructed, but the code here checks again.
                                    # But refactoring all this to still share the hard work
                                    # (doit()) is complicated.
                                    self.generate_field_validation(namespace, field, vn)
                                    out('break;')
            out('')

            self.generate_static_values(data_type, tag_name, tag_name + '.')
            out('')

            # Generate toString(), toStringMultiline(), toJson(), fromJson() methods.
            with self.block('public String toString()'):
                out('return "%s." + _writer.writeToString(this, false);' % class_name)
            with self.block('public String toStringMultiline()'):
                out('return "%s." +  _writer.writeToString(this, true);' % class_name)
            with self.block('public String toJson(Boolean longForm)'):
                out('return _writer.writeToString(this, longForm);')
            out('public static %s fromJson(String s)' % class_name)
            out('    throws JsonReadException')
            with self.block():
                out('return _reader.readFully(s);')

    def generate_static_values(self, data_type, class_name, value_prefix=''):
        """Generate _values Map with static initializer (used by JSON reader)."""
        out = self.emit
        out('private static final java.util.HashMap<String,%s> _values;' % class_name)
        with self.block('static'):
            out('_values = new java.util.HashMap<String,%s>();' % class_name)
            for field in data_type.fields:
                out('_values.put("%s", %s%s);' % (field.name, value_prefix, camelcase(field.name)))

    def generate_enum_values(self, data_type, do_doc=False, last_sep=';'):
        """Generate enum values."""
        out = self.emit
        count = len(data_type.all_fields)
        for i, field in enumerate(data_type.all_fields):
            if do_doc:
                self.generate_doc(field.doc)
            if i + 1 == count:
                sep = last_sep
            else:
                sep = ','
            if field is data_type.catch_all_field:
                assert isinstance(field.data_type, Void), field.data_type
                sep += '  // *catch_all'
            elif not isinstance(field.data_type, Void):
                sep += '  // %s' % field.data_type.name
            out(camelcase(field.name) + sep)

    def generate_json_writer(self, namespace, class_name, data_type):
        """Generate the JsonWriter for a struct class."""
        out = self.emit
        if data_type.is_member_of_enumerated_subtypes_tree():
            # Accessor for the writer (bridge for strunion writing).
            with self.block('public JsonWriter getWriter()'):
                out('return %s._writer;' % class_name)
        out('static final JsonWriter<%s> _writer = new JsonWriter<%s>()' %
            (class_name, class_name))
        with self.bsemi():
            ancestors = get_ancestors(data_type)
            out('public final void write(%s x, JsonGenerator g)' % class_name)
            out(' throws IOException')
            with self.block():
                if data_type.is_member_of_enumerated_subtypes_tree():
                    out('JsonWriter w = x.getWriter();')
                    with self.block('if (w != this)'):
                        out('w.write(x, g);')
                        out('return;')
                out('g.writeStartObject();')
                tags = [tag for tag, _ in ancestors if tag]
                if tags:
                    out('g.writeStringField(".tag", "%s");' % '.'.join(tags))
                for _, dt in ancestors:
                    out('%s._writer.writeFields(x, g);' % classname(dt.name))
                out('g.writeEndObject();')

            out('public final void writeFields(%s x, JsonGenerator g)' % class_name)
            out(' throws IOException')
            with self.block():
                for field in data_type.fields:
                    var_name = 'x.' + camelcase(field.name)
                    with self.block('if (%s != null)' % var_name):
                        self.generate_write_field(namespace, field, var_name)

    def generate_write_field(self, namespace, field, var_name):
        """Generate code to write a single field."""
        out = self.emit
        ft = field.data_type
        # For strings, numbers and booleans use a shorthand method.
        if is_string_type(ft):
            out('g.writeStringField("%s", %s);' % (field.name, var_name))
        elif is_numeric_type(ft):
            out('g.writeNumberField("%s", %s);' % (field.name, var_name))
        elif is_boolean_type(ft):
            out('g.writeBooleanField("%s", %s);' % (field.name, var_name))
        else:
            # General case.
            out('g.writeFieldName("%s");' % field.name)
            self.generate_write_value(namespace, field.data_type, var_name)

    def generate_write_value(self, namespace, data_type, var_name, level=0):
        """Generate code to write a single value."""
        out = self.emit
        nullable = is_nullable_type(data_type)
        if nullable:
            data_type = data_type.data_type
        if is_string_type(data_type):
            out('g.writeString(%s);' % var_name)
        elif is_numeric_type(data_type):
            out('g.writeNumber(%s);' % var_name)
        elif is_boolean_type(data_type):
            out('g.writeBoolean(%s);' % var_name)
        elif is_composite_type(data_type):
            out('%s._writer.write(%s, g);' % (maptype(namespace, data_type), var_name))
        elif is_timestamp_type(data_type):
            out('writeDateIso(%s, g);' % var_name)
        elif is_binary_type(data_type):
            out('g.writeString(com.dropbox.core.util.StringUtil.base64Encode(%s));' % var_name)
        elif is_list_type(data_type):
            item_name = 'item' if level == 0 else 'item%d' % level
            out('g.writeStartArray();')
            with self.block('for (%s %s: %s)' %
                            (maptype(namespace, data_type.data_type), item_name, var_name)):
                with self.block('if (%s != null)' % item_name):
                    self.generate_write_value(namespace, data_type.data_type, item_name, level+1)
            out('g.writeEndArray();')
        else:
            out('throw new IOException("XXX Don\'t know how to write a %s");' %
                maptype(namespace, data_type))

    def generate_json_reader(self, namespace, class_name, data_type):
        """Generate the JsonReader for a struct class."""
        out = self.emit
        with self.bsemi('public static final JsonReader<%s> _reader = new JsonReader<%s>()' %
                        (class_name, class_name)):

            out('')
            out('public final %s read(JsonParser parser)' % class_name)
            out('    throws IOException, JsonReadException')
            with self.block():
                out('%s result;' % class_name)
                out('JsonReader.expectObjectStart(parser);')
                if data_type.is_member_of_enumerated_subtypes_tree():
                    # We need the .tag field first.
                    out('String[] tags = readTags(parser);')
                    out('result = readFromTags(tags, parser);')
                else:
                    out('result = readFields(parser);')
                out('JsonReader.expectObjectEnd(parser);')
                out('return result;')

            if data_type.is_member_of_enumerated_subtypes_tree():
                out('')
                out('public final %s readFromTags(String[] tags, JsonParser parser)' % class_name)
                out('    throws IOException, JsonReadException')
                with self.block():
                    ancestors = get_ancestors(data_type)
                    depth = len(ancestors) - 1
                    if depth >= 1:
                        with self.block('if (tags != null)'):
                            out('assert tags.length >= %d;' % depth)
                            for i, (tag, dt) in enumerate(ancestors[1:]):
                                out('assert "%s".equals(tags[%d]);' % (tag, i))
                    if data_type.has_enumerated_subtypes():
                        with self.block('if (tags != null && tags.length > %d)' % depth):
                            for field in data_type.get_enumerated_subtypes():
                                with self.block('if ("%s".equals(tags[%d]))' % (field.name, depth)):
                                    out('return %s._reader.readFromTags(tags, parser);' %
                                        classname(field.data_type.name))
                            out('// If no match, fall back to base class')
                    out('return readFields(parser);')

            out('')
            out('public final %s readFields(JsonParser parser)' % class_name)
            out('    throws IOException, JsonReadException')
            with self.block():
                out('%s result = new %s();' % (class_name, class_name))
                with self.block('while (parser.getCurrentToken() == JsonToken.FIELD_NAME)'):
                    out('String fieldName = parser.getCurrentName();')
                    out('parser.nextToken();')
                    pfx = ''  # This becomes 'else ' after the first field.
                    for field in data_type.all_fields:
                        with self.block('%sif ("%s".equals(fieldName))' %
                                        (pfx, field.name)):
                            pfx = 'else '
                            self.generate_read_field(namespace, field,
                                                     'result.%s' % camelcase(field.name))
                    out('%s{ JsonReader.skipValue(parser); }' % pfx)
                out('return result;')

            # Generate validate() method.
            out('')
            with self.block('public final void validate(%s value)' % class_name):
                if data_type.parent_type:
                    out('%s._reader.validate(value);' % maptype(namespace, data_type.parent_type))
                for field in data_type.fields:
                    self.generate_field_validation(namespace, field)

    def generate_field_validation(self, namespace, field, value_name=None):
        """Generate validation code for one field.

        The value_name argument must be None for a struct, and the
        full value name for a union.
        """
        out = self.emit
        is_struct = (value_name is None)

        def todo(ft):
            """Decide whether doit() will emit any code."""
            if is_composite_type(ft):
                return True
            if is_list_type(ft):
                return True
            if is_numeric_type(ft):
                return ft.min_value is not None or ft.max_value is not None
            if is_string_type(ft):
                return (ft.min_length is not None or ft.max_length is not None or
                        ft.pattern is not None)
            if is_boolean_type(ft) or is_timestamp_type(ft) or is_binary_type(ft):
                return False
            return True

        def doit(ft, vn, dn=None, level=0):
            """Actually emit the validation code for the field.

            ft: field type
            vn: variable name
            dn: optional display name (defaults to vn)
            level: optional recursion level

            Note: This is recursive for list types.
            """
            if dn is None:
                dn = vn
            if is_composite_type(ft):
                out('%s._reader.validate(%s);' % (maptype(namespace, ft), vn))
            elif is_list_type(ft):
                if ft.min_items is not None:
                    with self.block('if (%s.size() < %s)' % (vn, mapvalue(namespace,
                                                                          ft, ft.min_items))):
                        out('throw new RuntimeException("List \'%s\' has fewer than %s items");' %
                            (dn, mapvalue(namespace, ft, ft.min_items)))
                if ft.max_items is not None:
                    with self.block('if (%s.size() > %s)' % (vn, mapvalue(namespace,
                                                                          ft, ft.max_items))):
                        out('throw new RuntimeException("List \'%s\' has more than %s items");' %
                            (dn, mapvalue(namespace, ft, ft.max_items)))
                xn = 'x' if level == 0 else 'x%d' % level
                with self.block('for (%s %s : %s)' % (maptype(namespace, ft.data_type), xn, vn)):
                    with self.block('if (%s == null)' % xn):
                        out('throw new RuntimeException("An item in list \'%s\' is null");' % dn)
                    doit(ft.data_type, xn, 'an item in list field %s' % dn, level+1)
            elif is_numeric_type(ft):
                if ft.min_value is not None:
                    with self.block('if (%s < %s)' % (vn, mapvalue(namespace, ft, ft.min_value))):
                        out('throw new RuntimeException("Number \'%s\' is smaller than %s");' %
                            (dn, mapvalue(namespace, ft, ft.min_value)))
                if ft.max_value is not None:
                    with self.block('if (%s > %s)' % (vn, mapvalue(namespace, ft, ft.max_value))):
                        out('throw new RuntimeException("Number \'%s\' is larger than %s");' %
                            (dn, mapvalue(namespace, ft, ft.max_value)))
            elif is_string_type(ft):
                if ft.min_length is not None:
                    with self.block('if (%s.length() < %d)' % (vn, ft.min_length)):
                        out('throw new RuntimeException("String \'%s\' is shorter than %s");' %
                            (dn, mapvalue(namespace, ft, ft.min_length)))
                if ft.max_length is not None:
                    with self.block('if (%s.length() > %d)' % (vn, ft.max_length)):
                        out('throw new RuntimeException("String \'%s\' is longer than %s");' %
                            (dn, mapvalue(namespace, ft, ft.max_length)))
                if ft.pattern is not None:
                    # TODO: Save the pattern as a static variable.
                    with self.block('if (!java.util.regex.Pattern.matches("\\\\A%s\\\\Z", %s))' %
                                    (ft.pattern.replace('\\', '\\\\'), vn)):
                        out('throw new RuntimeException("String \'%s\' does not match pattern");' %
                            dn)
            elif is_boolean_type(ft) or is_timestamp_type(ft) or is_binary_type(ft):
                pass  # Nothing to do for these
            else:
                out('throw new RuntimeException("XXX Don\'t know how to validate %s: type %s");' %
                    (dn, ft.name))

        ft = field.data_type
        nullable = is_nullable_type(ft)
        if nullable:
            ft = ft.data_type
        if is_struct:
            vn = 'value.' + camelcase(field.name)
        else:
            vn = value_name
        if nullable:
            if todo(ft):
                with self.block('if (%s != null)' % vn):
                    doit(ft, vn)
        elif is_struct and field.has_default:
            # TODO: There's a slight problem here.  After calling
            # .validate() the default value is filled in, but this
            # also means that the value will be serialized.  We may
            # have to add a flag to validate() indicating whether
            # defaults should be filled in or not.  The default should
            # be filled in when validating an incoming value (i.e. the
            # result of an API call) but it should not be filled in
            # when validating an outgoing value (i.e. the argument to
            # an API call).
            with self.block('if (%s == null)' % vn):
                out('%s = %s;' % (vn, mapvalue(namespace, ft, field.default)))
            if todo(ft):
                with self.block('else'):
                    doit(ft, vn)
        else:
            with self.block('if (%s == null)' % vn):
                out('throw new RuntimeException("Required value for \'%s\' is null");' %
                    camelcase(field.name))
            doit(ft, vn)

    def generate_read_field(self, namespace, field, var_name):
        """Generate the code to read one field."""
        out = self.emit
        ft = field.data_type
        out('%s = %s' % (var_name, mapreader(namespace, ft)))
        with self.indent():
            out('.readField(parser, "%s", %s);' % (field.name, var_name))

    def generate_doc(self, doc, route_formatter=None):
        """Generate a Javadoc comment."""
        out = self.emit
        if doc:
            if route_formatter is None:
                route_formatter = lambda v: routename(v)
            handler = lambda tag, val: doc_ref_handler(tag, val, route_formatter)
            doc = self.process_doc(doc, handler)
            out('/**')
            self.emit_wrapped_text(doc, initial_prefix=' * ', subsequent_prefix=' * ')
            out(' */')
