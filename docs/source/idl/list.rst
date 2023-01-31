==============
 Entity Index
==============


* ``void``: :py:class:`yace.idl.base`; A void, that is, the type signaling no type

* ``dec``: :py:class:`yace.idl.constants`; Representation of a an integer literal in decimal

* ``define``: :py:class:`yace.idl.constants`; C MACROS, one of biggest headaches when it comes to FFI interfaces,

* ``enum``: :py:class:`yace.idl.constants`; Representation of enumeration values, note that literals on the

* ``hex``: :py:class:`yace.idl.constants`; Representation of a hexi-decimal constant

* ``bool``: :py:class:`yace.idl.datatypes`; A boolean, at least 8 bits wide, equivalent to the C99 "_Bool" and available

* ``char``: :py:class:`yace.idl.datatypes`; A character, at least 8 bits wide.

* ``f32``: :py:class:`yace.idl.datatypes`; A floating point numerical value, possibly 32 bits wide

* ``f64``: :py:class:`yace.idl.datatypes`; A floating point numerical value, possibly 64 bits wide

* ``i16``: :py:class:`yace.idl.datatypes`; A basic data type: signed fixed-width integer; 16 bits wide.

* ``i32``: :py:class:`yace.idl.datatypes`; A basic data type: signed fixed-width integer; 32 bits wide.

* ``i64``: :py:class:`yace.idl.datatypes`; A basic data type: signed fixed-width integer; 64 bits wide.

* ``i8``: :py:class:`yace.idl.datatypes`; A basic data type: signed fixed-width integer; 8 bits wide.

* ``int``: :py:class:`yace.idl.datatypes`; The integer commonly used for error-handling, non-fixed width.

* ``string``: :py:class:`yace.idl.datatypes`; A string pointer

* ``u16``: :py:class:`yace.idl.datatypes`; A basic data type: signed fixed-width integer; 16 bits wide.

* ``u32``: :py:class:`yace.idl.datatypes`; A basic data type: unsigned fixed-width integer; 32 bits wide.

* ``u64``: :py:class:`yace.idl.datatypes`; A basic data type: unsigned fixed-width integer; 64 bits wide.

* ``u8``: :py:class:`yace.idl.datatypes`; A basic data type: signed fixed-width integer; 8 bits wide.

* ``bitfield``: :py:class:`yace.idl.structtypes`; Representation of a bitfield, that is a partitioning of a fixed-width

* ``bits``: :py:class:`yace.idl.structtypes`; Representation of a :class:`.Bitfield` member.

* ``field``: :py:class:`yace.idl.structtypes`; A representation of :class:`yace.idl.Struct` and

* ``struct``: :py:class:`yace.idl.structtypes`; A representation of a struct definition

* ``union``: :py:class:`yace.idl.uniontypes`; Representation of enumerations / collections of constants

* ``fun``: :py:class:`yace.idl.functiontypes`; Function declarations

* ``fun_ptr``: :py:class:`yace.idl.functiontypes`; Function pointer declarations

* ``param``: :py:class:`yace.idl.functiontypes`; Function parameter

* ``ret``: :py:class:`yace.idl.functiontypes`; Function return type

