#!/usr/bin/env python3
"""Fail-closed arm64e compiler probe for XNU's ucred.cr_label PAC schema."""

import argparse
from pathlib import Path
import re
import shlex
import subprocess
import sys


SOURCE = Path(__file__).resolve().with_name("fixtures") / "xnu-ptrauth-auth-null.c"
PROBES = ("load", "store", "clear", "copy", "init")
SSA = r"%[\w.$-]+"
KEY = 2  # ASDA / process-independent data
DISC = 0x8B90  # ptrauth_string_discriminator("ucred.cr_label")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def body(ir, name):
    match = re.search(rf"^define\b[^\n]*@probe_{name}\([^\n]*\{{\n(.*?)^}}", ir, re.M | re.S)
    require(match, f"missing probe_{name} in LLVM IR")
    return match[1]


def ordinary_init_copies_unsigned_null(ir, text):
    # Apple Clang may lower the local initializer to a constant aggregate
    # copied to the stack, instead of emitting separate field stores.
    pattern = (r"^(@[\w.$-]+) = private unnamed_addr constant %struct\.slot "
               r"\{ i64 42, ptr null \}(?:, align 8)?$")
    for constant in re.findall(pattern, ir, re.M):
        copy = re.search(rf"@llvm\.memcpy\.p0\.p0\.i64\(ptr [^,\n]*?({SSA}), "
                         rf"ptr [^,\n]*?{re.escape(constant)}, i64 16, i1 false\)", text)
        if copy and re.search(rf"^\s*{re.escape(copy[1])} = alloca %struct\.slot\b", text, re.M) and \
                re.search(rf"@consume_slot\(ptr [^,\n]*{re.escape(copy[1])}\)", text):
            return True
    return False


def validate(ir, *, auth_null):
    require(re.search(r'^target triple = "arm64e-apple-ios27\.0(?:\.0)?"$', ir, re.M),
            "unexpected target triple")
    for name in PROBES:
        text = body(ir, name)
        if re.search(r"\b(?:br|switch)\s+|\bselect\s", text):
            require(not auth_null, f"{name}: conditional path could skip pointer authentication")
        if not auth_null:
            if name in ("clear", "init"):
                unsigned_null = "store ptr null," in text or (
                    name == "init" and ordinary_init_copies_unsigned_null(ir, text))
                require(unsigned_null and "@llvm.ptrauth.sign(" not in text,
                        f"{name}: ordinary qualifier did not store unsigned null")
            else:
                require(re.search(r"\bicmp (?:eq|ne) ptr .*\bnull\b", text) and
                        re.search(r"@llvm\.ptrauth\.(?:sign|auth|resign)\(", text),
                        f"{name}: ordinary qualifier lacks null bypass or PAC operation")
            continue

        def invariant(condition, message):
            require(condition, f"{name}: {message}")

        # Follow the operation through ptrtoint/inttoptr, rather than just
        # checking for an intrinsic somewhere in the function.
        ptr_as_int = dict(re.findall(rf"({SSA}) = ptrtoint ptr ({SSA}) to i64", text))
        int_as_ptr = dict(re.findall(rf"({SSA}) = inttoptr i64 ({SSA}) to ptr", text))
        loads = dict(re.findall(rf"({SSA}) = load ptr, ptr ({SSA})\b", text))
        stores = re.findall(rf"store ptr ({SSA}|null), ptr ({SSA})\b", text)
        blend = {
            result: ptr_as_int.get(operand)
            for result, operand in re.findall(
                rf"({SSA}) = [^\n]*@llvm\.ptrauth\.blend\(i64 ({SSA}), i64 {DISC}\)", text)
        }

        def operation(op, args):
            return re.search(rf"({SSA}) = [^\n]*@llvm\.ptrauth\.{op}\({args}\)", text)

        def signed(op, args):
            match = operation(op, args)
            invariant(match, f"missing {op} with expected PAC key and operands")
            return match.groups()

        def stored(result, field):
            return field is not None and any(int_as_ptr.get(p) == result and addr == field
                                             for p, addr in stores)

        def loaded(integer, field):
            return field is not None and loads.get(ptr_as_int.get(integer)) == field

        invariant(all(value != "null" for value, _ in stores), "stores an unsigned null")
        if name == "load":
            result, operand, discr = signed("auth", rf"i64 ({SSA}), i32 {KEY}, i64 ({SSA})")
            invariant(loaded(operand, blend.get(discr)), "authentication does not use loaded field and its address")
            invariant(any(value == result and f"ret ptr {p}\n" in text for p, value in int_as_ptr.items()),
                      "load does not return the authenticated value")
        elif name == "copy":
            data_args = rf"i64 ({SSA}), i32 {KEY}, i64 ({SSA})"
            resign = operation("resign", rf"{data_args}, i32 {KEY}, i64 ({SSA})")
            if resign:
                result, operand, src, dst = resign.groups()
            else:
                authed, operand, src = signed("auth", data_args)
                result, to_sign, dst = signed("sign", data_args)
                invariant(to_sign == authed, "copy signs a value other than the authenticated pointer")
            invariant(blend.get(src) != blend.get(dst) and loaded(operand, blend.get(src)) and
                      stored(result, blend.get(dst)), "copy does not re-sign from source to destination address")
        else:
            value = rf"({SSA})" if name == "store" else "(0)"
            result, operand, discr = signed("sign", rf"i64 {value}, i32 {KEY}, i64 ({SSA})")
            if name == "store":
                header = re.search(r"^define\b[^\n]*@probe_store\([^\n]*", ir, re.M)
                parameters = re.findall(SSA, header[0])
                invariant(len(parameters) == 2 and ptr_as_int.get(operand) == parameters[1],
                          "write does not sign the supplied pointer")
            invariant(stored(result, blend.get(discr)), "signed value not stored at the matching address")


def validate_asm(asm):
    for name in PROBES:
        match = re.search(rf"^_probe_{name}:[^\n]*\n(.*?)(?=^\s*\.globl|\Z)", asm, re.M | re.S)
        require(match, f"missing probe_{name} in assembly")
        ops = re.findall(r"^\s+([a-z][a-z0-9.]*)\s", match[1], re.M)
        if name in ("load", "copy"):
            require("autda" in ops and "brk" in ops and ops.index("autda") < ops.index("brk"),
                    f"{name}: missing data-key authentication followed by failure trap")
        if name != "load":
            require("pacda" in ops, f"{name}: missing data-key signing in assembly")
        require(not any(op in ops for op in ("cbz", "cbnz", "tbz", "tbnz")),
                f"{name}: unexpected test-and-branch in authenticated-null fixture")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clang", help="path to the compiler, or a name in PATH")
    parser.add_argument("--out", type=Path, required=True, help="new evidence directory")
    parser.add_argument("--self-test", action="store_true", help="test checker with explicit intrinsics instead of testing compiler capability")
    args = parser.parse_args()
    try:
        out = args.out.resolve()
        out.mkdir(parents=True)

        def run(command, log):
            print(shlex.join(command), flush=True)
            with log.open("w") as handle:
                rc = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT).returncode
            require(rc == 0, f"compiler exited {rc}; see {log}")

        run([args.clang, "--version"], out / "compiler.txt")
        variants = (("ordinary", 0), ("reference", 2) if args.self_test else ("auth-null", 1))
        compile_errors = []
        for name, schema in variants:
            base = [args.clang, "-target", "arm64e-apple-ios27.0", "-mkernel", "-ffreestanding",
                    "-O2", f"-DSCHEMA={schema}", "-S", str(SOURCE)]
            ir = out / f"{name}.ll"
            try:
                run(base + ["-emit-llvm", "-o", str(ir)], out / f"{name}-ir.log")
                run(base + ["-o", str(out / f"{name}.s")], out / f"{name}-asm.log")
                validate(ir.read_text(), auth_null=bool(schema))
                if schema:
                    validate_asm((out / f"{name}.s").read_text())
                print(f"PASS {name} codegen")
            except ValueError as exc:
                compile_errors.append(f"{name}: {exc}")
        require(not compile_errors, "; ".join(compile_errors))
        if args.self_test:
            def reject(ir, label):
                try:
                    validate(ir, auth_null=True)
                except ValueError as exc:
                    print(f"PASS rejected {label}: {exc}")
                    return
                raise ValueError(f"checker accepted {label}")

            reject((out / "ordinary.ll").read_text(), "three-argument schema as auth-null")
            reference = (out / "reference.ll").read_text()
            reject(reference.replace("@llvm.ptrauth.sign(i64 0, i32 2,", "@llvm.ptrauth.sign(i64 0, i32 3,"),
                   "wrong null-signing key")
            reject(reference.replace("i64 35728)", "i64 35729)"), "wrong discriminator")
            reject(reference.replace("@llvm.ptrauth.resign(", "@not_ptrauth_resign("), "copy without re-signing")
            try:
                validate_asm((out / "reference.s").read_text().replace("\tbrk\t", "\tnop ; "))
            except ValueError as exc:
                print(f"PASS rejected missing authentication trap: {exc}")
            else:
                raise ValueError("checker accepted missing authentication trap")
            print("SELF-TEST only; four-argument qualifier not tested")
        else:
            print("PASS qualifier/codegen probe; not a kernel ABI, linker, or runtime qualification")
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
