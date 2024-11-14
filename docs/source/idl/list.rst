.. _sec-idl-list:

Entity Listing
==============


* ``dec``: :py:class:`yace.idl.constants.Dec`; Representation of a an integer literal in decimal

* ``define``: :py:class:`yace.idl.constants.Define`; C MACROS, one of biggest headaches when it comes to FFI interfaces,

* ``enum``: :py:class:`yace.idl.constants.Enum`; Representation of enumeration values, note that literals on the

* ``enum_value``: :py:class:`yace.idl.constants.EnumValue`; Representation of values in class`yace.idl.constants.Enum`.

* ``hex``: :py:class:`yace.idl.constants.Hex`; Representation of a hexadecimal constant

* ``str``: :py:class:`yace.idl.constants.String`; Representation of a literal string e.g. in C

* ``array_tspec``: :py:class:`yace.idl.datatypes.Array`; Fixed-length arrays

* ``bool_tspec``: :py:class:`yace.idl.datatypes.Bool`; A boolean, at least 8 bits wide

* ``string_tspec``: :py:class:`yace.idl.datatypes.CString`; A string pointer

* ``char_tspec``: :py:class:`yace.idl.datatypes.Char`; A character; at least 8 bits wide.

* ``enum_tspec``: :py:class:`yace.idl.datatypes.Enumeration`; Elaborated / Enum / Enumeration

* ``f32_tspec``: :py:class:`yace.idl.datatypes.F32`; Floating point numerical value, possibly 32 bits wide

* ``f64_tspec``: :py:class:`yace.idl.datatypes.F64`; Floating point numerical value, possibly 64 bits wide

* ``function_pointer_tspec``: :py:class:`yace.idl.datatypes.FunctionPointer`; Function pointer

* ``i_tspec``: :py:class:`yace.idl.datatypes.I`; Signed integer at least 16 bits wide.

* ``i16_tspec``: :py:class:`yace.idl.datatypes.I16`; Signed integer exactly 16 bits wide.

* ``i32_tspec``: :py:class:`yace.idl.datatypes.I32`; Signed integer exactly 32 bits wide.

* ``i64_tspec``: :py:class:`yace.idl.datatypes.I64`; Signed integer exactly 64 bits wide.

* ``i8_tspec``: :py:class:`yace.idl.datatypes.I8`; Signed integer exactly 8 bits wide.

* ``il_tspec``: :py:class:`yace.idl.datatypes.ILong`; Signed integer at least 32 bits wide.

* ``ill_tspec``: :py:class:`yace.idl.datatypes.ILongLong`; Signed integer at least 64 bits wide.

* ``ih_tspec``: :py:class:`yace.idl.datatypes.IShort`; Signed integer at least 8 bits wide.

* ``isize_tspec``: :py:class:`yace.idl.datatypes.ISize`; Signed Size-type

* ``pointer_tspec``: :py:class:`yace.idl.datatypes.Pointer`; Pointer

* ``record_tspec``: :py:class:`yace.idl.datatypes.Record`; Record; struct, union or enum

* ``u_tspec``: :py:class:`yace.idl.datatypes.U`; Unsigned integer at least 16 bits wide.

* ``u16_tspec``: :py:class:`yace.idl.datatypes.U16`; Unsigned integer exactly 16 bits wide.

* ``u32_tspec``: :py:class:`yace.idl.datatypes.U32`; Unsigned integer exactly 32 bits wide.

* ``u64_tspec``: :py:class:`yace.idl.datatypes.U64`; Unsigned integer exactly 64 bits wide.

* ``u8_tspec``: :py:class:`yace.idl.datatypes.U8`; Unsigned integer exactly 8 bits wide.

* ``ul_tspec``: :py:class:`yace.idl.datatypes.ULong`; Unsigned integer at least 32 bits wide.

* ``ull_tspec``: :py:class:`yace.idl.datatypes.ULongLong`; Unsigned integer at least 64 bits wide.

* ``us_tspec``: :py:class:`yace.idl.datatypes.UShort`; Unsigned integer at least 8 bits wide.

* ``usize_tspec``: :py:class:`yace.idl.datatypes.USize`; Unsigned Size-type

* ``void_tspec``: :py:class:`yace.idl.datatypes.Void`; A void, that is, the type signaling no type

* ``void_pointer_tspec``: :py:class:`yace.idl.datatypes.VoidPtr`; A void-pointer, that is, point to anything (including nothing)

* ``bitfield_decl``: :py:class:`yace.idl.derivedtypes.Bitfield`; A representation of a bit-field within a class`yace.idl.Struct`

* ``bitfield_struct_decl``: :py:class:`yace.idl.derivedtypes.BitfieldStruct`; A struct where all the fields / members are bitfields.

* ``field_decl``: :py:class:`yace.idl.derivedtypes.Field`; A representation of class`yace.idl.Struct` and

* ``struct_decl``: :py:class:`yace.idl.derivedtypes.Struct`; A representation of a struct definition

* ``union_decl``: :py:class:`yace.idl.derivedtypes.Union`; Representation of enumerations / collections of constants

* ``function_decl``: :py:class:`yace.idl.functiontypes.Function`; Function declarations

* ``function_pointer_decl``: :py:class:`yace.idl.functiontypes.FunctionPointer`; Function pointer declarations by convention of

* ``parameter_decl``: :py:class:`yace.idl.functiontypes.Parameter`; Function parameter

* ``include_stmt``: :py:class:`yace.idl.directives.IncludeDirective`; Something like

