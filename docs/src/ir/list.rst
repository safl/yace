.. _sec-ir-list:

Entity Listing
==============


* ``dec``: :py:class:`yace.ir.constants.Dec`; Representation of a an integer literal in decimal

* ``define``: :py:class:`yace.ir.constants.Define`; C MACROS, one of biggest headaches when it comes to FFI interfaces,

* ``enum``: :py:class:`yace.ir.constants.Enum`; Representation of enumeration values, note that literals on the

* ``enum_value``: :py:class:`yace.ir.constants.EnumValue`; Representation of values in class`yace.ir.constants.Enum`.

* ``hex``: :py:class:`yace.ir.constants.Hex`; Representation of a hexadecimal constant

* ``str``: :py:class:`yace.ir.constants.String`; Representation of a literal string e.g. in C

* ``array_tspec``: :py:class:`yace.ir.datatypes.Array`; Fixed-length arrays

* ``bool_tspec``: :py:class:`yace.ir.datatypes.Bool`; A boolean, at least 8 bits wide

* ``string_tspec``: :py:class:`yace.ir.datatypes.CString`; A string pointer

* ``char_tspec``: :py:class:`yace.ir.datatypes.Char`; A character; at least 8 bits wide.

* ``enum_tspec``: :py:class:`yace.ir.datatypes.Enumeration`; Elaborated / Enum / Enumeration

* ``f32_tspec``: :py:class:`yace.ir.datatypes.F32`; Floating point numerical value, possibly 32 bits wide

* ``f64_tspec``: :py:class:`yace.ir.datatypes.F64`; Floating point numerical value, possibly 64 bits wide

* ``function_pointer_tspec``: :py:class:`yace.ir.datatypes.FunctionPointer`; Function pointer

* ``i_tspec``: :py:class:`yace.ir.datatypes.I`; Signed integer at least 16 bits wide.

* ``i16_tspec``: :py:class:`yace.ir.datatypes.I16`; Signed integer exactly 16 bits wide.

* ``i32_tspec``: :py:class:`yace.ir.datatypes.I32`; Signed integer exactly 32 bits wide.

* ``i64_tspec``: :py:class:`yace.ir.datatypes.I64`; Signed integer exactly 64 bits wide.

* ``i8_tspec``: :py:class:`yace.ir.datatypes.I8`; Signed integer exactly 8 bits wide.

* ``il_tspec``: :py:class:`yace.ir.datatypes.ILong`; Signed integer at least 32 bits wide.

* ``ill_tspec``: :py:class:`yace.ir.datatypes.ILongLong`; Signed integer at least 64 bits wide.

* ``ih_tspec``: :py:class:`yace.ir.datatypes.IShort`; Signed integer at least 8 bits wide.

* ``isize_tspec``: :py:class:`yace.ir.datatypes.ISize`; Signed Size-type

* ``pointer_tspec``: :py:class:`yace.ir.datatypes.Pointer`; Pointer

* ``record_tspec``: :py:class:`yace.ir.datatypes.Record`; Record; struct, union or enum

* ``u_tspec``: :py:class:`yace.ir.datatypes.U`; Unsigned integer at least 16 bits wide.

* ``u16_tspec``: :py:class:`yace.ir.datatypes.U16`; Unsigned integer exactly 16 bits wide.

* ``u32_tspec``: :py:class:`yace.ir.datatypes.U32`; Unsigned integer exactly 32 bits wide.

* ``u64_tspec``: :py:class:`yace.ir.datatypes.U64`; Unsigned integer exactly 64 bits wide.

* ``u8_tspec``: :py:class:`yace.ir.datatypes.U8`; Unsigned integer exactly 8 bits wide.

* ``ul_tspec``: :py:class:`yace.ir.datatypes.ULong`; Unsigned integer at least 32 bits wide.

* ``ull_tspec``: :py:class:`yace.ir.datatypes.ULongLong`; Unsigned integer at least 64 bits wide.

* ``us_tspec``: :py:class:`yace.ir.datatypes.UShort`; Unsigned integer at least 8 bits wide.

* ``usize_tspec``: :py:class:`yace.ir.datatypes.USize`; Unsigned Size-type

* ``void_tspec``: :py:class:`yace.ir.datatypes.Void`; A void, that is, the type signaling no type

* ``void_pointer_tspec``: :py:class:`yace.ir.datatypes.VoidPtr`; A void-pointer, that is, point to anything (including nothing)

* ``bitfield_decl``: :py:class:`yace.ir.derivedtypes.Bitfield`; A representation of a bit-field within a class`yace.ir.Struct`

* ``bitfield_struct_decl``: :py:class:`yace.ir.derivedtypes.BitfieldStruct`; A struct where all the fields / members are bitfields.

* ``field_decl``: :py:class:`yace.ir.derivedtypes.Field`; A representation of class`yace.ir.Struct` and

* ``struct_decl``: :py:class:`yace.ir.derivedtypes.Struct`; A representation of a struct definition

* ``union_decl``: :py:class:`yace.ir.derivedtypes.Union`; Representation of enumerations / collections of constants

* ``function_decl``: :py:class:`yace.ir.functiontypes.Function`; Function declarations

* ``function_pointer_decl``: :py:class:`yace.ir.functiontypes.FunctionPointer`; Function pointer declarations by convention of

* ``parameter_decl``: :py:class:`yace.ir.functiontypes.Parameter`; Function parameter

* ``include_stmt``: :py:class:`yace.ir.directives.IncludeDirective`; Something like
