"""
The entities in the **yace** Interface Definition are enherit the
:class:`.Entity` and mix-in common attributes.

* Base-classes: :class:`.Entity` / :class:`.Typespec`

* Mixin-attributes: :class:`.Named` / :class:`.Documented` / :class:`.Typed`

The above are defined below.
"""
import logging as log
import re
import typing
from collections import ChainMap


def all_annotations(cls) -> ChainMap:
    """
    Returns a dictionary-like ChainMap that includes annotations for all
    attributes defined in the given 'cls' or inherited from superclasses.

    Courtesy of SO:
    https://stackoverflow.com/questions/63903901/how-can-i-access-to-annotations-of-parent-class
    """
    return ChainMap(
        *(c.__annotations__ for c in cls.__mro__ if "__annotations__" in c.__dict__)
    )


class Entity(object):
    """
    A baseclass for all entities in the Yace Interface Definition Language.

    It is defined as the Python dataclasses got in the way, this instead as a
    fixed set of functionality:

    * Construct by passing a dict of arguments
    * Do a runtime type using is_valid()
    * Allow inheritance / subclassing with optional and required arguments

    Constructor raises ValueError for missing required arguments.
    """

    cls: str  # The Yace-IDL constructor keyword
    lbl: typing.List[str] = ["nope"]  # Labels
    ant: typing.Optional[dict]  # User-defined annotations of any kind

    def __init__(self, args: typing.Optional[typing.Dict] = None):
        self.annotations = all_annotations(self.__class__)

        if args is None:
            args = dict()
        args["ant"] = args.get("ant", dict())

        self.all = list(self.annotations)
        self.required = []
        self.optional = []
        for attr in self.annotations.keys():
            if hasattr(self, attr):
                self.optional.append(attr)
            else:
                self.required.append(attr)

        missing = list(set(self.required) - set(list(args)))
        unexpected = list(set(args) - set(self.all))

        if missing or unexpected:
            log.info(f"ant: {self.annotations}")
            log.info(f"all: {self.all}")
            log.info(f"req: {self.required}")
            log.info(f"opt: {self.optional}")
            log.info(f"missing: {missing}")
            log.info(f"unexpected: {unexpected}")
            raise ValueError(
                f"{self.__class__.__name__}() constructor arguments; "
                f"is missing: {missing}, "
                f"got unexpected: {unexpected}"
            )

        for key, val in args.items():
            setattr(self, key, val)

    def is_valid(self):
        """
        Here is what this validates

        * Field-specific checks from subclass or mixin such as ``is_valid_sym()``

        * Generic check of attribute-instances matching theirannotations
        """

        for attr, atype in self.annotations.items():
            if not getattr(attr, "get_origin", False):  # skip typing.*
                continue
            if isinstance(attr, atype):  # is_valid
                continue

            return False, f"Bad type({atype}) of attribute({attr})"

        for attr in self.all:
            attr_checker = getattr(self, f"is_valid_{attr}", False)
            if not attr_checker:
                continue
            valid, message = attr_checker()
            if valid:
                continue

            return valid, message

        return True, "OK"

    def as_dict(self):
        """Returns the Entity represented as a dict"""

        return {attr: getattr(self, attr) for attr in self.all}

    def __repr__(self):
        return str(self.as_dict())


class Typespec(Entity):
    """
    All entities is-a :class:`.Entity`
    """

    # Lack of type
    void: bool = False

    # Boolean and textual datatypes
    boolean: bool = False  # Boolean type, since C99: _Bool / true / false
    character: bool = False  # Character type, in C: char / 'k'

    # Numeral types
    size: bool = False  # Size-types; size_t, ssize_t
    integer: bool = False  # Integer types; int
    real: bool = False  # Floating point number e.g. float, double

    # Numerical types (Qualifiers and Modifiers)
    unsigned: bool = False  # Type-modifier for the integer datatype
    width: typing.Optional[int] = None  # integer type width
    width_fixed: bool = False  # True: has an exact bit-width

    # Derived types
    union: bool = False  # union <id> { ... }
    struct: bool = False  # struct <id> { ... }
    sym: typing.Optional[str] = None  # symbol / tag of structs and unions

    # General Qualifiers and Modifiers
    const: bool = False  # Access-qualifier for all types:  'const'
    static: bool = False  # Storage-qualifier for all types: 'static'
    pointer: int = 0  # Pointer-type for all types: '*'
    array: int = 0  # Array-type for all types: '[]'


class Documented(object):
    """
    Attribute-mixin; adding a required 'doc' describing the :class:`.Entity`
    """

    doc: str


class Named(object):
    """
    Attribute-mixin; adding a required 'sym' to be used as identifier
    """

    sym: str

    def is_valid_sym(self):
        """Check whether the symbol is a valid C identifier"""

        if self.sym is None:
            return False, f"Invalid attr: sym == None; for {self.as_dict()}"

        match = re.match(r"[_a-z][_a-z0-9]{0,30}", str(self.sym))
        if match:
            return True, "OK"

        return False, f"Invalid attr: '{self.sym}'; for {self.as_dict()}"


class Typed(object):
    """
    Attribute-mixin; adding a reqried "has-a" relation to :class:`.Typespec`
    """

    typ: Typespec
