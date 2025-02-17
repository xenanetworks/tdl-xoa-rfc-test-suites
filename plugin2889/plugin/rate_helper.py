from decimal import Decimal


def calc_l2_bit_rate_from_l1_bit_rate(bps_rate_l1: Decimal, frame_size: int, interframe_gap: int) -> Decimal:
    return bps_rate_l1 * frame_size / (frame_size + interframe_gap)


def calc_l2_frame_rate(bps_rate_l2: Decimal, frame_size: int) -> Decimal:
    return bps_rate_l2 / Decimal(8) / frame_size


def calc_l1_bit_rate(frame_rate: int, frame_size: int, interframe_gap: int) -> Decimal:
    return frame_rate * Decimal(8) * Decimal(frame_size + interframe_gap)
