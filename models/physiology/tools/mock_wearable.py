import argparse
import asyncio
import csv
import random
import struct
import time

from dms_physiology.protocol import PacketCodec
from dms_physiology.types import Channel, PpgPacket
from dms_physiology.waveform import WaveformConfig, generate_ppg


async def handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    args: argparse.Namespace,
    packets: list[tuple[PpgPacket, list[int]]],
) -> None:
    start_time = time.monotonic()
    sample_rate = 125  # assuming default
    samples_sent = 0

    with open(args.csv, "w", newline="") as f:
        csv_writer = csv.writer(f)
        csv_writer.writerow(["first_sample_index", "send_ns"])

        for packet, _ in packets:
            now = time.monotonic()
            elapsed = now - start_time

            if args.disconnect_at > 0 and elapsed > args.disconnect_at:
                writer.close()
                import contextlib
                with contextlib.suppress(Exception):
                    await writer.wait_closed()
                if args.reconnect_after > 0:
                    await asyncio.sleep(args.reconnect_after)
                    # wait for new connection, but this function only handles one client session
                    # To truly reconnect, the server needs to accept a new connection.
                    # Exiting this handler allows the server to accept another connection.
                    return
                else:
                    return

            payload = PacketCodec.encode(packet)
            
            # 8.9 Verify:
            assert PacketCodec.decode(payload) == packet

            samples_sent += packet.sample_count
            ideal_time = samples_sent / sample_rate

            if not args.firehose:
                interval_idx = int(ideal_time // 0.030)
                target_time = start_time + (interval_idx + 1) * 0.030
                if args.jitter:
                    target_time += random.uniform(-0.005, 0.005)
                
                delay = target_time - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)

            length_prefix = struct.pack("!H", len(payload))
            try:
                writer.write(length_prefix + payload)
                await writer.drain()
            except ConnectionError:
                break

            send_ns = time.perf_counter_ns()
            csv_writer.writerow([packet.first_sample_index, send_ns])

    writer.close()
    import contextlib
    with contextlib.suppress(Exception):
        await writer.wait_closed()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Mock Wearable TCP Transmitter")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--mtu", type=int, default=3)
    parser.add_argument("--disconnect-at", type=float, default=0.0)
    parser.add_argument("--reconnect-after", type=float, default=0.0)
    parser.add_argument("--firehose", action="store_true")
    parser.add_argument("--jitter", action="store_true")
    parser.add_argument("--csv", default="latency.csv")

    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--hr-profile", default="constant")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--flatline", action="store_true")
    parser.add_argument("--contact-loss", action="store_true")
    parser.add_argument("--saturation", action="store_true")
    parser.add_argument("--fifo-overflow", action="store_true")
    
    args = parser.parse_args()

    config = WaveformConfig(
        seconds=args.seconds,
        batch_size=args.mtu,
        hr_profile=args.hr_profile,
        seed=args.seed,
        flatline=args.flatline,
        contact_loss=args.contact_loss,
        saturation=args.saturation,
        fifo_overflow=args.fifo_overflow,
        channels=Channel.RED | Channel.INFRARED,
    )
    
    packets = list(generate_ppg(config))

    async def client_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await handle_client(reader, writer, args, packets)

    server = await asyncio.start_server(client_handler, args.host, args.port)
    print(f"Mock wearable listening on {args.host}:{args.port}")

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    import contextlib
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
