.. _sec-idl-list:

================
 Entity Listing
================


* ``void``: :py:class:`yace.idl.base.Void`; A void, that is, the type signaling no type

* ``dec``: :py:class:`yace.idl.constants.Dec`; Representation of a an integer literal in decimal

* ``define``: :py:class:`yace.idl.constants.Define`; C MACROS, one of biggest headaches when it comes to FFI interfaces,

* ``enum``: :py:class:`yace.idl.constants.Enum`; Representation of enumeration values, note that literals on the

* ``enum_value``: :py:class:`yace.idl.constants.EnumValue`; Representation of values in class`yace.idl.constants.Enum`.

* ``hex``: :py:class:`yace.idl.constants.Hex`; Representation of a hexi-decimal constant

* ``str``: :py:class:`yace.idl.constants.String`; Representation of a literal string e.g. in C

* ``bool``: :py:class:`yace.idl.datatypes.Bool`; A boolean, at least 8 bits wide, equivalent to the C99 "_Bool" and available

* ``char``: :py:class:`yace.idl.datatypes.Char`; A character, at least 8 bits wide.

* ``f32``: :py:class:`yace.idl.datatypes.F32`; A floating point numerical value, possibly 32 bits wide

* ``f64``: :py:class:`yace.idl.datatypes.F64`; A floating point numerical value, possibly 64 bits wide

* ``i16``: :py:class:`yace.idl.datatypes.I16`; A basic data type signed fixed-width integer; 16 bits wide.

* ``i32``: :py:class:`yace.idl.datatypes.I32`; A basic data type signed fixed-width integer; 32 bits wide.

* ``i64``: :py:class:`yace.idl.datatypes.I64`; A basic data type signed fixed-width integer; 64 bits wide.

* ``i8``: :py:class:`yace.idl.datatypes.I8`; A basic data type signed fixed-width integer; 8 bits wide.

* ``int``: :py:class:`yace.idl.datatypes.Int`; The integer commonly used for error-handling, non-fixed width.

* ``size``: :py:class:`yace.idl.datatypes.SizeSigned`; The C API emitter could produce

* ``string``: :py:class:`yace.idl.datatypes.String`; A string pointer

* ``u16``: :py:class:`yace.idl.datatypes.U16`; A basic data type signed fixed-width integer; 16 bits wide.

* ``u32``: :py:class:`yace.idl.datatypes.U32`; A basic data type unsigned fixed-width integer; 32 bits wide.

* ``u64``: :py:class:`yace.idl.datatypes.U64`; A basic data type unsigned fixed-width integer; 64 bits wide.

* ``u8``: :py:class:`yace.idl.datatypes.U8`; A basic data type signed fixed-width integer; 8 bits wide.

* ``bitfield``: :py:class:`yace.idl.structtypes.Bitfield`; Representation of a bitfield, that is a partitioning of a fixed-width

* ``bits``: :py:class:`yace.idl.structtypes.Bits`; Representation of a class`.Bitfield` member.

* ``field``: :py:class:`yace.idl.structtypes.Field`; A representation of class`yace.idl.Struct` and

* ``struct``: :py:class:`yace.idl.structtypes.Struct`; A representation of a struct definition

* ``union``: :py:class:`yace.idl.uniontypes.Union`; Representation of enumerations / collections of constants

* ``fun``: :py:class:`yace.idl.functiontypes.Function`; Function declarations

* ``fun_ptr``: :py:class:`yace.idl.functiontypes.FunctionPointer`; Function pointer declarations

* ``param``: :py:class:`yace.idl.functiontypes.Parameter`; Function parameter

* ``ret``: :py:class:`yace.idl.functiontypes.ReturnType`; Function return type

