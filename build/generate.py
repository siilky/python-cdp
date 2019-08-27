from dataclasses import dataclass
from enum import Enum
import itertools
import json
import logging
import operator
import os
from pathlib import Path
from textwrap import dedent, indent as tw_indent
import typing

import inflection


log_level = getattr(logging, os.environ.get('LOG_LEVEL', 'info').upper())
logging.basicConfig(level=log_level)
logger = logging.getLogger('generate')

SHARED_HEADER = '''DO NOT EDIT THIS FILE

This file is generated from the CDP specification. If you need to make changes,
edit the generator and regenerate all of the modules.'''

INIT_HEADER = '''\'\'\'
{}
\'\'\'

'''.format(SHARED_HEADER)

MODULE_HEADER = '''\'\'\'
{}

Domain: {{}}
Experimental: {{}}
\'\'\'

from cdp.util import T_JSON_DICT
from dataclasses import dataclass
import enum
import typing


'''.format(SHARED_HEADER)


def indent(s: str, n: int):
    ''' A shortcut for ``textwrap.indent`` that always uses spaces. '''
    return tw_indent(s, n * ' ')

def clear_dirs(package_path: Path):
    ''' Remove generated code. '''
    def rmdir(path):
        for subpath in path.iterdir():
            if subpath.is_file():
                subpath.unlink()
            elif subpath.is_dir():
                rmdir(subpath)
        path.rmdir()

    try:
        (package_path / '__init__.py').unlink()
    except FileNotFoundError:
        pass

    for subpath in package_path.iterdir():
        if subpath.is_dir():
            rmdir(subpath)


def inline_doc(description) -> str:
    ''' Generate an inline doc, e.g. ``#: This type is a ...`` '''
    if not description:
        return ''

    lines = ['#: {}\n'.format(l) for l in description.split('\n')]
    return ''.join(lines)


def docstring(description: typing.Optional[str]) -> str:
    ''' Generate a docstring from a description. '''
    if not description:
        return ''

    return dedent("'''\n{}\n'''").format(description)


def ref_to_python(ref: str) -> str:
    '''
    Convert a CDP ``$ref`` to the name of a Python type.

    For a dotted ref, the part before the dot is snake cased.
    '''
    if '.' in ref:
        domain, subtype = ref.split('.')
        ref = '{}.{}'.format(inflection.underscore(domain), subtype)
    return f"{ref}"


class CdpPrimitiveType(Enum):
    ''' All of the CDP types that map directly to a Python type annotation. '''
    any = 'typing.Any'
    array = 'typing.List'
    boolean = 'bool'
    integer = 'int'
    number = 'float'
    object = 'dict'
    string = 'str'


@dataclass
class CdpItemType:
    ''' The type of a repeated item. '''
    type: str
    ref: str

    @property
    def py_annotation(self) -> str:
        if self.type:
            annotation = CdpPrimitiveType[self.type].value
        else:
            py_ref = ref_to_python(self.ref)
            annotation = f"'{py_ref}'"

        return annotation

    @classmethod
    def from_json(cls, type) -> 'CdpItemType':
        return cls(type.get('type'), type.get('$ref'))


@dataclass
class CdpProperty:
    ''' A property belonging to a non-primitive CDP type. '''
    name: str
    description: str
    type: str
    ref: str
    enum: typing.List[str]
    items: CdpItemType
    optional: bool

    @property
    def py_name(self) -> str:
        ''' Get this property's Python name. '''
        return inflection.underscore(self.name)

    @property
    def py_annotation(self) -> str:
        ''' This property's Python type annotation. '''
        if self.type == 'array':
            ann = f'typing.List[{self.items.py_annotation}]'
        elif self.ref:
            py_ref = ref_to_python(self.ref)
            ann = f"'{py_ref}'"
        else:
            ann = CdpPrimitiveType[self.type].value
        if self.optional:
            ann = f'typing.Optional[{ann}]'
        return ann

    @classmethod
    def from_json(cls, property) -> 'CdpProperty':
        ''' Instantiate a CDP property from a JSON object. '''
        return cls(
            property['name'],
            property.get('description'),
            property.get('type'),
            property.get('$ref'),
            property.get('enum'),
            CdpItemType.from_json(property['items']) if 'items' in property else None,
            property.get('optional', False),
        )

    def generate_decl(self) -> str:
        ''' Generate the code that declares this property. '''
        code = inline_doc(self.description)
        # todo handle dependencies later
        # elif '$ref' in prop and '.' not in prop_ann:
        #     # If the type lives in this module and is not a type that refers
        #     # to itself, then add it to the set of children so that
        #     # inter-class dependencies can be resolved later on.
        #     children.add(prop_ann)
        code += f'{self.py_name}: {self.py_annotation}'
        if self.optional:
            code += ' = None'
        return code

    def generate_to_json(self, dict_: str, use_self: bool=True) -> str:
        ''' Generate the code that exports this property to the specified JSON
        dict. '''
        self_ref = 'self.' if use_self else ''
        if self.items:
            if self.items.ref:
                assign = f"{dict_}['{self.name}'] = " \
                         f"[i.to_json() for i in {self_ref}{self.py_name}]"
            else:
                raise NotImplementedError()
        else:
            if self.ref:
                assign = f"{dict_}['{self.name}'] = " \
                         f"{self_ref}{self.py_name}.to_json()"
            else:
                assign = f"{dict_}['{self.name}'] = {self_ref}{self.py_name}"
        if self.optional:
            code = dedent(f'''\
                if {self_ref}{self.py_name} is not None:
                    {assign}''')
        else:
            code = assign
        return code

    def generate_from_json(self) -> str:
        ''' Generate the code that creates an instance from a JSON dict named
        ``json``. '''
        # todo this is one of the few places where a real dependency is created
        # (most of the deps are type annotations and can be avoided by quoting
        # the annotation)
        if self.items:
            if self.items.ref:
                py_ref = ref_to_python(self.items.ref)
                expr = f"[{py_ref}.from_json(i) for i in json['{self.name}']]"
            else:
                raise NotImplemented()
        else:
            if self.ref:
                py_ref = ref_to_python(self.ref)
                expr = f"{py_ref}.from_json(json['{self.name}'])"
            else:
                expr = f"json['{self.name}']"
        if self.optional:
            expr = f"{expr} if '{self.name}' in json else None"
        return expr


@dataclass
class CdpType:
    ''' A top-level CDP type. '''
    id: str
    description: str
    type: str
    enum: typing.List[str]
    properties: typing.List[CdpProperty]

    @classmethod
    def from_json(cls, type) -> 'CdpType':
        ''' Instantiate a CDP type from a JSON object. '''
        return cls(
            type['id'],
            type.get('description'),
            type['type'],
            type.get('enum'),
            [CdpProperty.from_json(p) for p in type.get('properties', list())],
        )

    def generate_code(self) -> str:
        ''' Generate Python code for this type. '''
        # todo handle exports and emitted types somewhere else?
        # exports = list()
        # exports.append(type_name)
        # emitted_types = set()
        logger.debug('Generating type %s: %s', self.id, self.type)
        if self.enum:
            return self.generate_enum_code()
        elif self.properties:
            return self.generate_class_code()
        else:
            return self.generate_primitive_code()

    def generate_primitive_code(self) -> str:
        ''' Generate code for a primitive type. '''
        py_type = CdpPrimitiveType[self.type].value

        def_to_json = dedent(f'''\
            def to_json(self) -> {py_type}:
                return self''')

        def_from_json = dedent(f'''\
            @classmethod
            def from_json(cls, json: {py_type}) -> '{self.id}':
                return cls(json)''')

        def_repr = dedent(f'''\
            def __repr__(self):
                return '{self.id}({{}})'.format(super().__repr__())''')

        code = f'class {self.id}({py_type}):\n'
        doc = docstring(self.description)
        if doc:
            code += indent(doc, 4) + '\n'
        code += indent(def_to_json, 4)
        code += '\n\n' + indent(def_from_json, 4)
        code += '\n\n' + indent(def_repr, 4)

        return code

    def generate_enum_code(self) -> str:
        '''
        Generate an "enum" type.

        Enums are handled by making a python class that contains only class
        members. Each class member is upper snaked case, e.g.
        ``MyTypeClass.MY_ENUM_VALUE`` and is assigned a string value from the
        CDP metadata.
        '''
        def_to_json = dedent('''\
            def to_json(self) -> str:
                return self.value''')

        def_from_json = dedent(f'''\
            @classmethod
            def from_json(cls, json: str) -> '{self.id}':
                return cls(json)''')

        code = f'class {self.id}(enum.Enum):\n'
        doc = docstring(self.description)
        if doc:
            code += indent(doc, 4) + '\n'
        for enum_member in self.enum:
            snake_case = inflection.underscore(enum_member).upper()
            enum_code = f'{snake_case} = "{enum_member}"\n'
            code += indent(enum_code, 4)
        code += '\n' + indent(def_to_json, 4)
        code += '\n\n' + indent(def_from_json, 4)

        return code

    def generate_class_code(self) -> str:
        '''
        Generate a class type.

        Top-level types that are defined as a CDP ``object`` are turned into Python
        dataclasses.
        '''
        # children = set()
        code = dedent(f'''\
            @dataclass
            class {self.id}:\n''')
        doc = docstring(self.description)
        if doc:
            code += indent(doc, 4) + '\n'

        # Emit property declarations. These are sorted so that optional
        # properties come after required properties, which is required to make
        # the dataclass constructor work.
        props = list(self.properties)
        props.sort(key=operator.attrgetter('optional'))
        code += '\n\n'.join(indent(p.generate_decl(), 4) for p in props)
        code += '\n\n'

        # Emit to_json() method. The properties are sorted in the same order as
        # above for readability.
        def_to_json = dedent('''\
            def to_json(self) -> T_JSON_DICT:
                json: T_JSON_DICT = dict()
        ''')
        assigns = (p.generate_to_json(dict_='json') for p in props)
        def_to_json += indent('\n'.join(assigns), 4)
        def_to_json += '\n'
        def_to_json += indent('return json', 4)
        code += indent(def_to_json, 4) + '\n\n'

        # Emit to_json() method. The properties are sorted in the same order as
        # above for readability.
        def_from_json = dedent(f'''\
            @classmethod
            def from_json(cls, json: T_JSON_DICT) -> '{self.id}':
                return cls(
        ''')
        def_from_json += indent('\n'.join(f'{p.name}={p.generate_from_json()},'
            for p in self.properties), 8)
        def_from_json += '\n'
        def_from_json += indent(')', 4)
        code += indent(def_from_json, 4)

        # todo we used to return a dict but i'm not sure if that's still needed?
        # return {
        #     'name': self.id,
        #     'code': code,
        #     Don't emit children that live in a different module. We assume that
        #     modules do not have cyclical dependencies on each other.
        #     'children': [c for c in children if '.' not in c],
        # }
        return code

    # Todo how to resolve dependencies?
    # The classes have dependencies on each other, so we have to emit them in
    # a specific order. If we can't resolve these dependencies after a certain
    # number of iterations, it suggests a cyclical dependency that this code
    # cannot handle.
    # tries_remaining = 1000
    # while classes:
    #     class_ = classes.pop(0)
    #     if not class_['children']:
    #         code += class_['code']
    #         emitted_types.add(class_['name'])
    #         continue
    #     if all(child in emitted_types for child in class_['children']):
    #         code += class_['code']
    #         emitted_types.add(class_['name'])
    #         continue
    #     classes.append(class_)
    #     tries_remaining -= 1
    #     if not tries_remaining:
    #         logger.error('Class resolution failed. Emitted these types: %s',
    #             emitted_types)
    #         logger.error('Class resolution failed. Cannot emit these types: %s',
    #             json.dumps(classes, indent=2))
    #         raise Exception('Failed to resolve class dependencies.'
    #             ' See output above.')


class CdpParameter(CdpProperty):
    ''' A parameter to a CDP command. '''
    def generate_code(self) -> str:
        ''' Generate the code for a parameter in a function call. '''
        if self.ref:
            py_type = "'{}'".format(ref_to_python(self.ref))
        else:
            py_type = CdpPrimitiveType[self.type].value
        if self.optional:
            py_type = f'typing.Optional[{py_type}]'
        code = f"{self.py_name}: {py_type}"
        if self.optional:
            code += ' = None'
        return code

    def generate_doc(self) -> str:
        ''' Generate the docstring for this parameter. '''
        desc = self.description.replace('`', '``')
        return f':param {self.py_name}: {desc}'


class CdpReturn(CdpProperty):
    ''' A return value from a CDP command. '''
    @property
    def py_annotation(self):
        if self.items:
            if self.items.ref:
                py_ref = ref_to_python(self.items.ref)
                ann = f"typing.List['{py_ref}']"
            else:
                raise NotImplementedError()
        else:
            if self.ref:
                raise NotImplementedError()
            else:
                raise NotImplementedError()

        return ann

    def generate_doc(self):
        ''' Generate the docstring for this return. '''
        desc = self.description.replace('`', '``')
        return f':returns: {desc}'


@dataclass
class CdpCommand:
    ''' A CDP command. '''
    name: str
    description: str
    experimental: bool
    parameters: typing.List[CdpParameter]
    returns: typing.List[CdpReturn]
    domain: str

    @property
    def py_name(self):
        ''' Get a Python name for this command. '''
        return inflection.underscore(self.name)

    @classmethod
    def from_json(cls, command, domain) -> 'CdpCommand':
        ''' Instantiate a CDP command from a JSON object. '''
        parameters = command.get('parameters', list())
        returns = command.get('returns', list())

        return cls(
            command['name'],
            command.get('description'),
            command.get('experimental', False),
            [CdpParameter.from_json(p) for p in parameters],
            [CdpReturn.from_json(r) for r in returns],
            domain,
        )

    def generate_code(self) -> str:
        ''' Generate code for a CDP command. '''
        # Generate the function header
        if len(self.returns) == 0:
            raise NotImplementedError()
        elif len(self.returns) == 1:
            ret_type = self.returns[0].py_annotation
        else:
            raise NotImplementedError()
        ret_type = f"typing.Generator[T_JSON_DICT,T_JSON_DICT,{ret_type}]"
        code = f'def {self.py_name}(\n'
        code += indent(
            ',\n'.join(p.generate_code() for p in self.parameters), 8)
        code += '\n'
        code += indent(f') -> {ret_type}:\n', 4)

        # Generate the docstring
        if self.description:
            doc = self.description + '\n\n'
        else:
            doc = ''
        doc += '\n'.join(p.generate_doc() for p in self.parameters)
        if len(self.returns) == 1:
            doc += '\n'
            doc += self.returns[0].generate_doc()
        elif len(self.returns) > 1:
            doc += '\n'
            raise NotImplementedError()
        if doc:
            code += indent(docstring(doc), 4)
            code += '\n'

        # Generate the function body
        code += indent('params: T_JSON_DICT = dict()', 4)
        code += '\n'
        assigns = (p.generate_to_json(dict_='params', use_self=False)
            for p in self.parameters)
        code += indent('\n'.join(assigns), 4)
        code += '\n'
        yield_code = dedent(f'''\
            cmd_dict: T_JSON_DICT = {{
                'method': '{self.domain}.{self.name}',
                'params': params,
            }}
            json = yield cmd_dict''')
        code += indent(yield_code, 4)
        code += '\n'
        if len(self.returns) == 0:
            raise NotImplementedError()
        else:
            expr = ', '.join(r.generate_from_json() for r in self.returns)
            code += indent(f'return {expr}', 4)
        return code


@dataclass
class CdpEvent:
    ''' A CDP event object. '''
    name: str
    description: str
    parameters: typing.List[CdpParameter]

    def generate_code(self) -> str:
        ''' Generate code for a CDP event. '''
        return 'TODO'


@dataclass
class CdpDomain:
    ''' A CDP domain contains metadata, types, commands, and events. '''
    domain: str
    experimental: bool
    dependencies: typing.List[str]
    types: typing.List[CdpType]
    commands: typing.List[CdpCommand]
    events: typing.List[CdpEvent]

    @property
    def module(self):
        ''' The name of the Python module for this CDP domain. '''
        return inflection.underscore(self.domain)

    @classmethod
    def from_json(cls, domain):
        ''' Instantiate a CDP domain from a JSON object. '''
        types = domain.get('types', list())
        commands = domain.get('commands', list())
        events = domain.get('events', list())

        return cls(
            domain['domain'],
            domain.get('experimental', False),
            domain.get('dependencies', list()),
            [CdpType.from_json(type) for type in types],
            [CdpCommand.from_json(command, domain['domain'])
                for command in commands],
            list(),
        )

    def generate_code(self) -> str:
        ''' Generate the Python module code for a given CDP domain. '''
        code = MODULE_HEADER.format(self.domain, self.experimental)
        item_iter = itertools.chain(
            iter(self.types),
            iter(self.commands),
            iter(self.events),
        )
        code += '\n\n\n'.join(item.generate_code() for item in item_iter)
        return code

        # todo update dependencies
        # The dependencies listed in the JSON don't match the actual dependencies
        # encountered when building the types. So we ignore the declared
        # dependencies and compute it ourself.
        # type_dependencies = set()
        # domain_types = domain.get('types', list())
        # for type_ in domain_types:
        #     for prop in type_.get('properties', list()):
        #         dependency = get_dependency(prop)
        #         if dependency:
        #             type_dependencies.add(dependency)
        # if type_dependencies:
        #     logger.debug('Computed type_dependencies: %s', ','.join(
        #         type_dependencies))
        #
        # event_dependencies = set()
        # domain_events = domain.get('events', list())
        # for event in domain_events:
        #     for param in event.get('parameters', list()):
        #         dependency = get_dependency(param)
        #         if dependency:
        #             event_dependencies.add(dependency)
        # if event_dependencies:
        #     logger.debug('Computed event_dependencies: %s', ','.join(
        #         event_dependencies))
        #
        # command_dependencies = set()
        # domain_commands = domain.get('commands', list())
        # for command in domain_commands:
        #     for param in command.get('parameters', list()):
        #         dependency = get_dependency(param)
        #         if dependency:
        #             command_dependencies.add(dependency)
        #     for return_ in command.get('returns', list()):
        #         dependency = get_dependency(return_)
        #         if dependency:
        #             command_dependencies.add(dependency)
        # if command_dependencies:
        #     logger.debug('Computed command_dependencies: %s', ','.join(
        #         command_dependencies))

        # types_path = module_path / 'types.py'
        # with types_path.open('w') as types_file:
        #     types_file.write(module_header.format(module_name, self.experimental))
        #     for dependency in sorted(type_dependencies):
        #         types_file.write(import_dependency(dependency))
        #     if type_dependencies:
        #         types_file.write('\n')
        #     type_exports, type_code = generate_types(domain_types)
        #     types_file.write(type_code)
        #
        # events_path = module_path / 'events.py'
        # with events_path.open('w') as events_file:
        #     events_file.write(module_header.format(module_name, self.experimental))
        #     events_file.write('from .types import *\n')
        #     for dependency in sorted(event_dependencies):
        #         events_file.write(import_dependency(dependency))
        #     if event_dependencies:
        #         events_file.write('\n')
        #     event_exports, event_code = generate_events(self.domain, domain_events)
        #     events_file.write(event_code)
        #
        # commands_path = module_path / 'commands.py'
        # with commands_path.open('w') as commands_file:
        #     commands_file.write(module_header.format(module_name, self.experimental))
        #     commands_file.write('from .types import *\n')
        #     for dependency in sorted(command_dependencies):
        #         commands_file.write(import_dependency(dependency))
        #     if command_dependencies:
        #         commands_file.write('\n')
        #     command_exports, command_code = generate_commands(self.domain, domain_commands)
        #     commands_file.write(command_code)

        # return module_name, type_exports, event_exports, command_exports


def parse(json_path, output_path):
    '''
    Parse JSON protocol description and return domain objects.

    :param Path json_path: path to a JSON CDP schema
    :param Path output_path: a directory path to create the modules in
    :returns: a list of CDP domain objects
    '''
    with json_path.open() as json_file:
        schema = json.load(json_file)
    version = schema['version']
    assert (version['major'], version['minor']) == ('1', '3')
    domains = list()
    for domain in schema['domains']:
        domains.append(CdpDomain.from_json(domain))
    return domains

######################################################
## All refactored code is above. Old code is below. ##
######################################################

def get_dependency(cdp_meta):
    if 'type' in cdp_meta and cdp_meta['type'] != 'array':
        return None

    if 'items' in cdp_meta and 'type' in cdp_meta['items']:
        return None

    if '$ref' in cdp_meta:
        type_ = cdp_meta['$ref']
    elif 'items' in cdp_meta and '$ref' in cdp_meta['items']:
        type_ = cdp_meta['items']['$ref']
    else:
        raise Exception('Cannot get dependency: {!r}'.format(cdp_meta))

    try:
        dependency, _ = type_.split('.')
        return dependency
    except ValueError:
        # Not a dependency on another module.
        return None


def import_dependency(dependency):
    module_name = inflection.underscore(dependency)
    return 'from ..{} import types as {}\n'.format(module_name, module_name)


def get_python_type(cdp_type):
    '''
    Generate a name for the Python type that corresponds to the the given CDP
    type.

    :param dict cdp_meta: CDP metadata for a type or property
    :returns: Python type as a string
    '''
    if 'type' in cdp_meta:
        cdp_type = cdp_meta['type']
        if cdp_type == 'array':
            py_type = 'typing.List'
            try:
                cdp_nested_type = get_python_type(cdp_meta['items'])
                if '.' in cdp_nested_type:
                    domain, subtype = cdp_nested_type.split('.')
                    cdp_nested_type = '{}.{}'.format(
                        inflection.underscore(domain), subtype)
                py_type += "['{}']".format(cdp_nested_type)
            except KeyError:
                # No nested type: ignore.
                pass
        else:
            py_type = {
                'any': 'typing.Any',
                'boolean': 'bool',
                'integer': 'int',
                'object': 'dict',
                'number': 'float',
                'string': 'str',
            }[cdp_type]
        return py_type

    if '$ref' in cdp_meta:
        prop_type = cdp_meta['$ref']
        if '.' in prop_type:
            # If the type lives in another module, then we need to
            # snake_case the module name and it should *not* be added to the
            # list of child classes that is used for dependency resolution.
            other_module, other_type = prop_type.split('.')
            prop_type = '{}.{}'.format(inflection.underscore(other_module),
                other_type)
        return prop_type

    raise Exception('Cannot get python type from CDP metadata: {!r}'.format(
        cdp_meta))


def is_builtin_type(python_type):
    return python_type in ('bool', 'int', 'dict', 'float', 'str')


def generate_events(domain, events):
    exports = list()
    code = '\n'
    for event in events:
        event_name = inflection.camelize(event['name'],
            uppercase_first_letter=True)
        parameters = event.get('parameters', list())
        code += '\n@dataclass\n'
        code += 'class {}:\n'.format(event_name)
        description = event.get('description')
        code += docstring(description)
        from_json = list()
        for parameter in parameters:
            name = parameter['name']
            snake_name = inflection.underscore(name)
            param_description = parameter.get('description')
            code += inline_doc(description, indent=4)
            if 'type' in parameter:
                param_decl = get_python_type(parameter)
            elif '$ref' in parameter:
                param_decl = parameter['$ref']
                if '.' in param_decl:
                    # If the type lives in another module, then we need to
                    # snake_case the module name and it should *not* be
                    # added to the list of child classes that is used for
                    # dependency resolution.
                    other_module, other_type = param_decl.split('.')
                    param_decl = '{}.{}'.format(
                        inflection.underscore(other_module), other_type)
            else:
                raise Exception('Cannot determing event parameter type:'
                    ' {!r}'.format(parameter))
            optional = parameter.get('optional', False)
            if optional:
                param_decl = 'typing.Optional[{}] = None'.format(param_decl)
            code += '    {}: {}\n\n'.format(snake_name, param_decl)
            from_json.append((name, snake_name, optional, make_return_code(parameter)))
        code += '    # These fields are used for internal purposes and are not part of CDP\n'
        code += "    _domain = '{}'\n".format(domain)
        code += "    _method = '{}'\n".format(event['name'])
        code += '\n'
        code += '    @classmethod\n'
        code += "    def from_json(cls, json: dict) -> '{}':\n".format(event_name)
        for name, snake_name, optional, snippet in from_json:
            if not optional:
                continue
            code += "        {} = {} if '{}' in json else None\n".format(
                snake_name, snippet, name)
        code += '        return cls(\n'
        for name, snake_name, optional, snippet in from_json:
            if optional:
                code += '            {}={},\n'.format(snake_name, snake_name)
            else:
                code += '            {}={},\n'.format(snake_name, snippet)
        code += '        )\n\n'
        exports.append(event_name)
    return exports, code


def generate_commands(domain_name, commands):
    '''
    Generate command definitions as Python code.

    :param str domain_name: the CDP domain name
    :param list commands: a list of CDP command definitions
    :returns: a tuple (list of exported types, code as string)
    '''
    code = '\n\n'
    for command in commands:
        command_name = command['name']
        method_name = inflection.underscore(command_name)
        description = command.get('description', '')
        arg_list = list()
        to_json = list()
        params = command.get('parameters', list())
        if params:
            description += '\n'
        for param in params:
            param_name = param['name']
            snake_name = inflection.underscore(param_name)
            param_type = get_python_type(param)
            param_decl = param_type
            if param.get('optional', False):
                param_decl = 'typing.Optional[{}] = None'.format(param_decl)
            arg_list.append('{}: {}'.format(snake_name, param_decl))
            description += '\n:param {}: {}'.format(snake_name,
                param.get('description', ''))
            if 'type' in param:
                if param['type'] != 'array':
                    json_code = '{}'.format(snake_name)
                elif '$ref' in param['items']:
                    subtype = get_python_type(param['items'])
                    json_code = '[i.to_json() for i in {}]'.format(snake_name)
                elif 'type' in param['items']:
                    subtype = get_python_type(param['items'])
                    json_code = '[i for i in {}]'.format(snake_name)
            else:
                json_code = '{}.to_json()'.format(snake_name)
            # convert = '' if is_builtin_type(param_type) else '.to_json()'
            to_json.append((param_name, snake_name, json_code,
                param.get('optional', False)))
        returns = command.get('returns', list())
        if len(returns) == 0:
            return_type = 'None'
        elif len(returns) == 1:
            return_type = get_python_type(returns[0])
            description += '\n:returns: {}'.format(
                returns[0].get('description', ''))
        else:
            return_type = 'dict'
            description += '\n:returns: a dict with the following keys:'
            for return_ in returns:
                optstr = '(Optional) ' if return_.get('optional', False) else ''
                description += '\n    * {}: {}{}'.format(return_['name'],
                    optstr, return_.get('description', ''))
        code += 'def {}('.format(method_name)
        if arg_list:
            code += '\n'
            for arg in arg_list:
                code += '        {},\n'.format(arg)
            code += '    '
        code += ') -> typing.Generator[T_JSON_DICT,T_JSON_DICT,{}]:\n'.format(return_type)
        code += docstring(description, indent=4)
        if to_json:
            code += '    params: T_JSON_DICT = {\n'
            for param_name, snake_name, json_code, optional in to_json:
                if optional:
                    continue
                code += "        '{}': {},\n".format(param_name, json_code)
            code += '    }\n'
            for param_name, snake_name, json_code, optional in to_json:
                if not optional:
                    continue
                code += '    if {} is not None:\n'.format(snake_name)
                code += "        params['{}'] = {}\n".format(param_name,
                    json_code)
        code += '    cmd_dict: T_JSON_DICT = {\n'
        code += "        'method': '{}.{}',\n".format(domain_name,
            command_name)
        if to_json:
            code += "        'params': params,\n"
        code += '    }\n'
        code += '    json = yield cmd_dict\n'
        if len(returns) == 1:
            return_ = returns[0]
            return_type = get_python_type(return_)
            code += '    return {}\n'.format(make_return_code(return_))
        elif len(returns) > 1:
            # we should be able to refactor the first part of this if block to have something
            # reusable, then we call that new thing inside of a loop in this elif block
            # the only difference here is printing key names and dict syntax
            code += '    result: T_JSON_DICT = {\n'
            # code += '    return {\n'
            for return_ in returns:
                if return_.get('optional', False):
                    continue
                return_type = get_python_type(return_)
                code += "        '{}': {},\n".format(return_['name'],
                    make_return_code(return_))
            code += '    }\n'
            for return_ in returns:
                if not return_.get('optional', False):
                    continue
                code += "    if '{}' in json:\n".format(return_['name'])
                code += "        result['{}'] = {}\n".format(return_['name'],
                    make_return_code(return_))
            code += '    return result\n'
        code += '\n\n'
    return [domain_name], code


def make_return_code(return_):
    '''
    Make a snippet of code that retuns a value inside of a ``from_json()``
    method.

    :param dict return_: the CDP metadata for the item to return
    :returns: a string
    '''
    return_name = return_['name']
    return_type = get_python_type(return_)
    if 'typing.List' in return_type:
        subtype = get_python_type(return_['items'])
        if subtype.startswith('typing.Any'):
            code = "[i for i in json['{}']]".format(return_name)
        elif 'type' in return_['items'] or is_builtin_type(subtype):
            code = "[{}(i) for i in json['{}']]".format(subtype, return_name)
        else:
            code = "[{}.from_json(i) for i in json['{}']]".format(subtype, return_name)
    elif is_builtin_type(return_type):
        code = "{}(json['{}'])".format(return_type, return_name)
    elif return_type.startswith('typing.Any'):
        code = "json['{}']".format(return_name)
    else:
        code = "{}.from_json(json['{}'])".format(return_type, return_name)
    return code


def generate_init(init_path, modules):
    '''
    Generate an ``__init__.py`` that exports the specified modules.

    :param Path init_path: a file path to create the init file in
    :param list[tuple] modules: a list of modules each represented as tuples
        of (name, list_of_exported_symbols)
    '''
    modules = [module[0] for module in modules]
    modules.sort()
    with init_path.open('w') as init_file:
        init_file.write(init_header)
        for submodule in ('types', 'events', 'commands'):
            for module in modules:
                init_file.write('import cdp.{}.{}\n'.format(module, submodule))
            init_file.write('\n')
        init_file.write('import cdp.util\n')


def main():
    ''' Main entry point. '''
    here = Path(__file__).parent.resolve()
    json_paths = [
        here / 'browser_protocol.json',
        here / 'js_protocol.json',
    ]
    output_path = here.parent / 'cdp'
    output_path.mkdir(exist_ok=True)
    clear_dirs(output_path)

    domains = list()
    for json_path in json_paths:
        logger.info('Parsing JSON file %s', json_path)
        domains.extend(parse(json_path, output_path))
    domains.sort(key=operator.attrgetter('domain'))

    for domain in domains:
        logger.info('Generating module: %s → %s.py', domain.domain,
            domain.module)
        module_path = output_path / f'{domain.module}.py'
        with module_path.open('w') as module_file:
            module_file.write(domain.generate_code())

    init_path = output_path / '__init__.py'
    # generate_init(init_path, domains)

    py_typed_path = output_path / 'py.typed'
    py_typed_path.touch()


if __name__ == '__main__':
    main()
