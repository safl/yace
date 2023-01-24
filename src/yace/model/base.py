import logging as log
import operator
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
    This is the baseclass for all entities in the Yace Interface Model
    (:class:`yace.model.model.Model`)

    It is defined as the Python dataclasses got in the way, this instead as a
    fixed set of functionality:

    * Construct by passing a dict of arguments
    * Do a runtime type using is_valid()
    * Allow inheritance / subclassing with optional and required arguments

    Constructor raises ValueError for missing required arguments.
    """

    cls: str  # The Yace-IDL constructor keyword
    lbl: typing.List[str] = ["nope"]  # Labels

    def __init__(self, args: dict = {}):
        self.annotations = all_annotations(self.__class__)

        self.all = list(self.annotations)
        self.required = []
        self.optional = []
        for attr in self.annotations.keys():
            if hasattr(self, attr):
                self.optional.append(attr)
            else:
                self.required.append(attr)

        missing = list(set(self.required) - set(list(args)))
        if missing:
            log.info(f"ant: {self.annotations}")
            log.info(f"all: {self.all}")
            log.info(f"req: {self.required}")
            log.info(f"opt: {self.optional}")
            raise ValueError(f"{self.__class__.__name__}() constr. missing: {missing}")

        for key, val in args.items():
            setattr(self, key, val)

    def is_valid(self):
        """Checks whether all attributes-instances match the annotations"""

        valid = all(
            [
                isinstance(getattr(self, a), t)
                for a, t in self.annotations.items()
                if getattr(t, "get_origin", False)
            ]
        )
        return valid, "OK" if valid else "Bad type of attribute"


class Typespec(Entity):
    """
    All entities is-a :class:`.Typespec`
    Stuff to consider:

    * .lbl should be list?
    """

    # Basic datatypes
    boolean: bool = False  # Boolean type, since C99: _Bool / true / false
    character: bool = False  # Character type, in C: char / 'k'
    integer: bool = False  # Integer types; int
    real: bool = False  # Floating point number e.g. float, double

    # Derived types
    union: bool = False  # union <id> { ... }
    struct: bool = False  # struct <id> { ... }

    # Qualifiers and Modifiers
    signed: bool = False  # Type-modifier for the integer datatype
    width: typing.Optional[int] = None  # fixed-width; int8_t / float / double

    const: bool = False  # Access-qualifier for all types:  'const'
    static: bool = False  # Storage-qualifier for all types: 'static'
    pointer: int = 0  # Pointer-type for all types: '*'
    array: int = 0  # Array-type for all types: '[]'

    lbl: typing.List[str] = ["typespec"]


class Void(Typespec):
    """A void, that is, the type signaling no type"""

    cls: str = "void"
    width: int = 0


class Declaration(Typespec):
    """Base-class for Derived Types and fields"""

    sym: str
    doc: str
