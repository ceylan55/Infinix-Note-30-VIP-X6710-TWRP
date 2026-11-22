using System;
using System.IO;
using System.Threading.Tasks;

class Lz4Legacy {
    // LZ4-HC (High Compression) block compressor producing LZ4 Legacy frame format (magic 0x184C2102, 8MB blocks)
    const int HASH_LOG = 17;
    const int HASH_SIZE = 1 << HASH_LOG;
    const int WINDOW_SIZE = 65536;
    const int WINDOW_MASK = WINDOW_SIZE - 1;
    const int MIN_MATCH = 4;
    const int MFLIMIT = 12;
    const int LASTLITERALS = 5;
    const int MAX_CHAIN = 64;

    static unsafe byte[] CompressBlockHC(byte[] src, int srcOff, int srcLen) {
        byte[] dst = new byte[srcLen + (srcLen / 255) + 64];
        int[] head = new int[HASH_SIZE];
        int[] prev = new int[WINDOW_SIZE];
        for (int i = 0; i < HASH_SIZE; i++) head[i] = -1;

        fixed (byte* sBase = src, dBase = dst)
        fixed (int* headPtr = head, prevPtr = prev) {
            byte* basePtr = sBase + srcOff;
            byte* ip = basePtr;
            byte* anchor = ip;
            byte* iend = basePtr + srcLen;
            byte* mflimit = iend - MFLIMIT;
            byte* matchlimit = iend - LASTLITERALS;
            byte* op = dBase;

            while (ip < mflimit) {
                int cur = (int)(ip - basePtr);
                uint v = *(uint*)ip;
                uint h = (v * 2654435761u) >> (32 - HASH_LOG);
                int matchIdx = headPtr[h];
                prevPtr[cur & WINDOW_MASK] = matchIdx;
                headPtr[h] = cur;

                int bestLen = MIN_MATCH - 1;
                int bestOff = 0;
                int bestBack = 0;

                int chain = MAX_CHAIN;
                int minIdx = Math.Max(0, cur - 65535);
                int anchorIdx = (int)(anchor - basePtr);
                int maxLen = (int)(matchlimit - ip);

                while (matchIdx >= minIdx && chain-- > 0) {
                    byte* mPtr = basePtr + matchIdx;
                    if (*(uint*)mPtr == v && mPtr[bestLen] == ip[bestLen]) {
                        int len = MIN_MATCH;
                        while (len < maxLen && ip[len] == mPtr[len]) len++;
                        int back = 0;
                        while (cur - back > anchorIdx && matchIdx - back > 0 && ip[-1 - back] == mPtr[-1 - back]) {
                            back++;
                        }
                        if (len + back > bestLen + bestBack) {
                            bestLen = len;
                            bestBack = back;
                            bestOff = cur - matchIdx;
                            if (len >= maxLen || len >= 256) break;
                        }
                    }
                    int nextIdx = prevPtr[matchIdx & WINDOW_MASK];
                    if (nextIdx >= matchIdx) break;
                    matchIdx = nextIdx;
                }

                if (bestLen >= MIN_MATCH) {
                    ip -= bestBack;
                    bestLen += bestBack;

                    int litLen = (int)(ip - anchor);
                    byte* tokenPtr = op++;
                    int token = (litLen >= 15) ? 0xF0 : (litLen << 4);
                    if (litLen >= 15) {
                        int rem = litLen - 15;
                        while (rem >= 255) { *op++ = 255; rem -= 255; }
                        *op++ = (byte)rem;
                    }
                    Buffer.MemoryCopy(anchor, op, litLen, litLen);
                    op += litLen;

                    *op++ = (byte)(bestOff & 0xFF);
                    *op++ = (byte)(bestOff >> 8);

                    int mCode = bestLen - MIN_MATCH;
                    if (mCode >= 15) {
                        *tokenPtr = (byte)(token | 15);
                        int rem = mCode - 15;
                        while (rem >= 255) { *op++ = 255; rem -= 255; }
                        *op++ = (byte)rem;
                    } else {
                        *tokenPtr = (byte)(token | mCode);
                    }

                    byte* matchEnd = ip + bestLen;
                    ip++;
                    int step = (bestLen > 64) ? 4 : 1;
                    while (ip < matchEnd && ip < mflimit) {
                        int idx = (int)(ip - basePtr);
                        uint hv = (*(uint*)ip * 2654435761u) >> (32 - HASH_LOG);
                        prevPtr[idx & WINDOW_MASK] = headPtr[hv];
                        headPtr[hv] = idx;
                        ip += step;
                    }
                    ip = matchEnd;
                    anchor = ip;
                } else {
                    ip++;
                }
            }

            int lastLit = (int)(iend - anchor);
            if (lastLit >= 15) {
                *op++ = 0xF0;
                int rem = lastLit - 15;
                while (rem >= 255) { *op++ = 255; rem -= 255; }
                *op++ = (byte)rem;
            } else {
                *op++ = (byte)(lastLit << 4);
            }
            Buffer.MemoryCopy(anchor, op, lastLit, lastLit);
            op += lastLit;

            int outLen = (int)(op - dBase);
            byte[] res = new byte[outLen];
            Buffer.BlockCopy(dst, 0, res, 0, outLen);
            return res;
        }
    }

    static int Main(string[] args) {
        if (args.Length < 2) {
            Console.WriteLine("Usage: Lz4Legacy <in.cpio> <out.lz4>");
            return 1;
        }
        byte[] input = File.ReadAllBytes(args[0]);
        int blockSize = 8 * 1024 * 1024;
        int numBlocks = (input.Length + blockSize - 1) / blockSize;
        byte[][] compressedBlocks = new byte[numBlocks][];

        Parallel.For(0, numBlocks, i => {
            int pos = i * blockSize;
            int chunk = Math.Min(blockSize, input.Length - pos);
            compressedBlocks[i] = CompressBlockHC(input, pos, chunk);
        });

        using (FileStream fs = new FileStream(args[1], FileMode.Create, FileAccess.Write))
        using (BinaryWriter bw = new BinaryWriter(fs)) {
            bw.Write(0x184C2102u); // LZ4 Legacy magic
            for (int i = 0; i < numBlocks; i++) {
                byte[] cBlock = compressedBlocks[i];
                bw.Write((uint)cBlock.Length);
                bw.Write(cBlock);
            }
        }
        Console.WriteLine("Compressed " + input.Length + " bytes -> " + new FileInfo(args[1]).Length + " bytes");
        return 0;
    }
}
