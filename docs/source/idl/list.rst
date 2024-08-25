.. _sec-idl-list:

Entity Listing
==============


* ``dec``: :py:class:`yace.idl.constants.Dec`; Representation of a an integer literal in decimal

* ``define``: :py:class:`yace.idl.constants.Define`; C MACROS, one of biggest headaches when it comes to FFI interfaces,

* ``enum``: :py:class:`yace.idl.constants.Enum`; Representation of enumeration values, note that literals on the

* ``enum_value``: :py:class:`yace.idl.constants.EnumValue`; Representation of values in class`yace.idl.constants.Enum`.

* ``hex``: :py:class:`yace.idl.constants.Hex`; Representation of a hexadecimal constant

* ``str``: :py:class:`yace.idl.constants.String`; Representation of a literal string e.g. in C

* ``bool``: :py:class:`yace.idl.datatypes.Bool`; A boolean, at least 8 bits wide

* ``char``: :py:class:`yace.idl.datatypes.Char`; A character; at least 8 bits wide.

* ``f32``: :py:class:`yace.idl.datatypes.F32`; Floating point numerical value, possibly 32 bits wide

* ``f64``: :py:class:`yace.idl.datatypes.F64`; Floating point numerical value, possibly 64 bits wide

* ``i``: :py:class:`yace.idl.datatypes.I`; Signed integer at least 16 bits wide.

* ``i16``: :py:class:`yace.idl.datatypes.I16`; Signed integer exactly 16 bits wide.

* ``i32``: :py:class:`yace.idl.datatypes.I32`; Signed integer exactly 32 bits wide.

* ``i64``: :py:class:`yace.idl.datatypes.I64`; Signed integer exactly 64 bits wide.

* ``i8``: :py:class:`yace.idl.datatypes.I8`; Signed integer exactly 8 bits wide.

* ``ih``: :py:class:`yace.idl.datatypes.IHalf`; Signed integer at least 8 bits wide.

* ``il``: :py:class:`yace.idl.datatypes.ILong`; Signed integer at least 32 bits wide.

* ``ill``: :py:class:`yace.idl.datatypes.ILongLong`; Signed integer at least 64 bits wide.

* ``isize``: :py:class:`yace.idl.datatypes.ISize`; Signed Size-type

* ``string``: :py:class:`yace.idl.datatypes.String`; A string pointer

* ``u``: :py:class:`yace.idl.datatypes.U`; Unsigned integer at least 16 bits wide.

* ``u16``: :py:class:`yace.idl.datatypes.U16`; Unsigned integer exactly 16 bits wide.

* ``u32``: :py:class:`yace.idl.datatypes.U32`; Unsigned integer exactly 32 bits wide.

* ``u64``: :py:class:`yace.idl.datatypes.U64`; Unsigned integer exactly 64 bits wide.

* ``u8``: :py:class:`yace.idl.datatypes.U8`; Unsigned integer exactly 8 bits wide.

* ``uh``: :py:class:`yace.idl.datatypes.UHalf`; Unsigned integer at least 8 bits wide.

* ``ul``: :py:class:`yace.idl.datatypes.ULong`; Unsigned integer at least 32 bits wide.

* ``ull``: :py:class:`yace.idl.datatypes.ULongLong`; Unsigned integer at least 64 bits wide.

* ``usize``: :py:class:`yace.idl.datatypes.USize`; Unsigned Size-type

* ``void``: :py:class:`yace.idl.datatypes.Void`; A void, that is, the type signaling no type

* ``void_ptr``: :py:class:`yace.idl.datatypes.VoidPtr`; A void-pointer, that is, point to anything (including nothing)

* ``bitfield``: :py:class:`yace.idl.derivedtypes.Bitfield`; Representation of a bitfield, that is a partitioning of a fixed-width

* ``bits``: :py:class:`yace.idl.derivedtypes.Bits`; Representation of a class`.Bitfield` member.

* ``field``: :py:class:`yace.idl.derivedtypes.Field`; A representation of class`yace.idl.Struct` and

* ``struct``: :py:class:`yace.idl.derivedtypes.Struct`; A representation of a struct definition

* ``union``: :py:class:`yace.idl.derivedtypes.Union`; Representation of enumerations / collections of constants

* ``fun``: :py:class:`yace.idl.functiontypes.Function`; Function declarations

* ``fun_ptr``: :py:class:`yace.idl.functiontypes.FunctionPointer`; Function pointer declarations

* ``param``: :py:class:`yace.idl.functiontypes.Parameter`; Function parameter

* ``ret``: :py:class:`yace.idl.functiontypes.ReturnType`; Function return type

