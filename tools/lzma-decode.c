/*
 * lzma-decode — unpack an EDK II LZMA guided section with EDK II's own decoder.
 *
 * Firmware volumes that a bootloader ships compacted (the FVMAIN_COMPACT file every
 * Qualcomm ABL carries) use EDK II's framing: a 13-byte LZMA-Alone header (5-byte
 * properties, 8-byte little-endian uncompressed size) followed by the raw LZMA stream.
 * General-purpose tools disagree with that framing — xz stops after a handful of bytes
 * and python-lzma reports corrupt input — so extraction has to use the same decoder the
 * firmware itself uses: MdePkg/LzmaCustomDecompressLib (here from the BaseTools SDK copy,
 * which is the identical 7-Zip SDK source).
 *
 * Usage:
 *   lzma-decode <input> <output> [--offset N]
 *   lzma-decode <input> <output> --raw-props <hex byte> --raw-dict <hex> --raw-size <n>
 *
 * Exit codes: 0 ok, 1 usage, 2 header error, 3 decode error.
 *
 * SPDX-License-Identifier: LGPL-2.1-or-later (7-Zip SDK portion) / BSD-2-Clause-Patent (this file)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#include "LzmaDec.h"

static void *SzAlloc(ISzAllocPtr p, size_t size)
{
  (void)p;
  return malloc(size);
}

static void SzFree(ISzAllocPtr p, void *address)
{
  (void)p;
  free(address);
}

static const ISzAlloc gAlloc = { SzAlloc, SzFree };

static uint8_t *read_file(const char *path, size_t *size_out)
{
  FILE *file = fopen(path, "rb");
  if (file == NULL) {
    fprintf(stderr, "lzma-decode: cannot open %s\n", path);
    exit(2);
  }
  if (fseek(file, 0, SEEK_END) != 0) {
    fprintf(stderr, "lzma-decode: seek failed on %s\n", path);
    exit(2);
  }
  long size = ftell(file);
  if (size < 0) {
    fprintf(stderr, "lzma-decode: tell failed on %s\n", path);
    exit(2);
  }
  rewind(file);
  uint8_t *data = malloc((size_t)size ? (size_t)size : 1);
  if (data == NULL || fread(data, 1, (size_t)size, file) != (size_t)size) {
    fprintf(stderr, "lzma-decode: short read on %s\n", path);
    exit(2);
  }
  fclose(file);
  *size_out = (size_t)size;
  return data;
}

static void hexdump_props(uint8_t props)
{
  unsigned lc = props % 9;
  unsigned rest = props / 9;
  unsigned lp = rest % 5;
  unsigned pb = rest / 5;
  fprintf(stderr, "lzma-decode: props 0x%02X -> lc=%u lp=%u pb=%u\n", props, lc, lp, pb);
}

int main(int argc, char **argv)
{
  if (argc < 3) {
    fprintf(stderr,
            "usage: %s <input> <output> [--offset N]\n"
            "       %s <input> <output> --raw-props P --raw-dict D --raw-size N\n",
            argv[0], argv[0]);
    return 1;
  }

  const char *input_path = argv[1];
  const char *output_path = argv[2];
  long offset = 0;
  long raw_size = -1;
  long raw_dict = -1;
  int raw_props = -1;
  ELzmaFinishMode finish_mode = LZMA_FINISH_END;

  for (int i = 3; i < argc; i++) {
    if (strcmp(argv[i], "--offset") == 0 && i + 1 < argc) {
      offset = strtol(argv[++i], NULL, 0);
    } else if (strcmp(argv[i], "--raw-size") == 0 && i + 1 < argc) {
      raw_size = strtol(argv[++i], NULL, 0);
    } else if (strcmp(argv[i], "--raw-dict") == 0 && i + 1 < argc) {
      raw_dict = strtol(argv[++i], NULL, 0);
    } else if (strcmp(argv[i], "--finish") == 0 && i + 1 < argc) {
      const char *mode = argv[++i];
      if (strcmp(mode, "any") == 0) {
        finish_mode = LZMA_FINISH_ANY;
      } else if (strcmp(mode, "end") == 0) {
        finish_mode = LZMA_FINISH_END;
      } else {
        fprintf(stderr, "lzma-decode: --finish takes any|end\n");
        return 1;
      }
    } else if (strcmp(argv[i], "--raw-props") == 0 && i + 1 < argc) {
      raw_props = (int)strtol(argv[++i], NULL, 0);
    } else {
      fprintf(stderr, "lzma-decode: unknown argument %s\n", argv[i]);
      return 1;
    }
  }

  size_t input_size = 0;
  uint8_t *input = read_file(input_path, &input_size);
  if (offset < 0 || (size_t)offset >= input_size) {
    fprintf(stderr, "lzma-decode: offset %ld outside %zu-byte input\n", offset, input_size);
    return 2;
  }

  const uint8_t *stream = input + offset;
  size_t stream_size = input_size - (size_t)offset;

  uint8_t props[5];
  size_t header_size;
  size_t dest_size;

  if (raw_props >= 0) {
    if (raw_size < 0 || raw_dict < 0) {
      fprintf(stderr, "lzma-decode: --raw-props needs --raw-size and --raw-dict\n");
      return 1;
    }
    props[0] = (uint8_t)raw_props;
    props[1] = (uint8_t)(raw_dict & 0xFF);
    props[2] = (uint8_t)((raw_dict >> 8) & 0xFF);
    props[3] = (uint8_t)((raw_dict >> 16) & 0xFF);
    props[4] = (uint8_t)((raw_dict >> 24) & 0xFF);
    dest_size = (size_t)raw_size;
    header_size = 0;
    fprintf(stderr, "lzma-decode: raw stream, %zu input bytes\n", stream_size);
  } else {
    if (stream_size < 13) {
      fprintf(stderr, "lzma-decode: %zu bytes is shorter than a 13-byte LZMA header\n", stream_size);
      return 2;
    }
    memcpy(props, stream, 5);
    uint64_t declared = 0;
    for (int i = 0; i < 8; i++) {
      declared |= (uint64_t)stream[5 + i] << (8 * i);
    }
    hexdump_props(props[0]);
    fprintf(stderr, "lzma-decode: dict 0x%02X%02X%02X%02X, uncompressed 0x%llX (%llu bytes)\n",
            props[4], props[3], props[2], props[1],
            (unsigned long long)declared, (unsigned long long)declared);
    if (declared == 0 || declared > (uint64_t)1 << 32) {
      fprintf(stderr, "lzma-decode: implausible uncompressed size, not an EDK II LZMA section?\n");
      return 2;
    }
    dest_size = (size_t)declared;
    header_size = 13;
  }

  uint8_t *output = malloc(dest_size ? dest_size : 1);
  if (output == NULL) {
    fprintf(stderr, "lzma-decode: out of memory for %zu bytes\n", dest_size);
    return 3;
  }

  SizeT dest_len = dest_size;
  SizeT src_len = stream_size - header_size;
  ELzmaStatus status = LZMA_STATUS_NOT_SPECIFIED;
  SRes result = LzmaDecode(output, &dest_len, stream + header_size, &src_len,
                           props, 5, finish_mode, &status, &gAlloc);
  if (result != SZ_OK) {
    fprintf(stderr, "lzma-decode: LzmaDecode failed with SRes=%d (status=%d), decoded %zu/%zu\n",
            (int)result, (int)status, (size_t)dest_len, dest_size);
    free(output);
    free(input);
    return 3;
  }

  FILE *out = fopen(output_path, "wb");
  if (out == NULL) {
    fprintf(stderr, "lzma-decode: cannot write %s\n", output_path);
    return 3;
  }
  if (fwrite(output, 1, dest_len, out) != dest_len) {
    fprintf(stderr, "lzma-decode: short write on %s\n", output_path);
    fclose(out);
    return 3;
  }
  fclose(out);

  fprintf(stderr, "lzma-decode: wrote %zu bytes to %s (consumed %zu of %zu input bytes, status=%d)\n",
          (size_t)dest_len, output_path, (size_t)src_len, stream_size - header_size, (int)status);
  free(output);
  free(input);
  return 0;
}
