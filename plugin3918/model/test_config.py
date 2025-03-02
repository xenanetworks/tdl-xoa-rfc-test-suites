from typing import List, Annotated
from pydantic import (
    ConfigError,
    Field,
    NonNegativeInt,
    BaseModel,
    PositiveInt,
    field_validator,
)

from ..utils.constants import (
    MIXED_DEFAULT_WEIGHTS,
    MIXED_PACKET_SIZE,
    PacketSizeType,
    IEEE_DEFAULT_LIST,
)


class FrameSizesOptions(BaseModel):
    field_0: NonNegativeInt = Field(56)
    field_1: NonNegativeInt = Field(60)
    field_14: NonNegativeInt = Field(9216)
    field_15: NonNegativeInt = Field(16360)

    @property
    def min(self) -> NonNegativeInt:
        return min(self.field_0, self.field_1, self.field_14, self.field_15)

    @property
    def max(self) -> NonNegativeInt:
        return max(self.field_0, self.field_1, self.field_14, self.field_15)


class FrameSizeConfiguration(BaseModel):
    # FrameSizes
    packet_size_type: PacketSizeType
    # FixedSizesPerTrial
    custom_packet_sizes: List[NonNegativeInt]
    fixed_packet_start_size: NonNegativeInt
    fixed_packet_end_size: NonNegativeInt
    fixed_packet_step_size: PositiveInt
    # VaryingSizesPerTrial
    varying_packet_min_size: NonNegativeInt
    varying_packet_max_size: NonNegativeInt
    mixed_sizes_weights: Annotated[List[NonNegativeInt], Field(validate_default=True)] = MIXED_DEFAULT_WEIGHTS
    mixed_length_config: FrameSizesOptions = FrameSizesOptions(
        field_0=56, field_1=60, field_14=9216, field_15=16360
    )

    @field_validator("mixed_sizes_weights", mode="before")
    def is_mixed_weights_valid(cls, v, values):
        if "packet_size_type" in values:
            if values["packet_size_type"] == PacketSizeType.MIX:
                if not v or len(v) != len(MIXED_DEFAULT_WEIGHTS):
                    raise ConfigError(
                        f"Not enough mixed weights; there should be {len(MIXED_DEFAULT_WEIGHTS)} number of mixed weights!"
                    )
                if not sum(v) == 100:
                    raise ConfigError(
                        f"The sum of packet weights must be 100% (is currently {sum(v)}%.)"
                    )
        return v

    @property
    def mixed_packet_length(self) -> List[int]:
        mix_size_length_dic = self.mixed_length_config.model_dump()
        return [
            MIXED_PACKET_SIZE[index]
            if not (mix_size_length_dic.get(f"field_{index}", 0))
            else mix_size_length_dic.get(f"field_{index}", 0)
            for index in range(len(MIXED_PACKET_SIZE))
        ]

    @property
    def mixed_average_packet_size(self) -> int:
        v = 0
        if self.packet_size_type == PacketSizeType.MIX:
            weighted_size = 0.0
            for index, size in enumerate(self.mixed_packet_length):
                weight = self.mixed_sizes_weights[index]
                weighted_size += size * weight
            v = round(weighted_size / 100.0)
        return v

    @property
    def packet_size_list(self) -> List[int]:
        packet_size_type = self.packet_size_type
        if packet_size_type == PacketSizeType.IEEE_DEFAULT:
            return IEEE_DEFAULT_LIST
        elif packet_size_type == PacketSizeType.CUSTOM_SIZES:
            return list(sorted(self.custom_packet_sizes))
        elif packet_size_type == PacketSizeType.MIX:
            return [self.mixed_average_packet_size]

        elif packet_size_type == PacketSizeType.RANGE:
            return list(
                range(
                    self.fixed_packet_start_size,
                    self.fixed_packet_end_size + self.fixed_packet_step_size,
                    self.fixed_packet_step_size,
                )
            )

        elif packet_size_type in {
            PacketSizeType.INCREMENTING,
            PacketSizeType.BUTTERFLY,
            PacketSizeType.RANDOM,
        }:
            return [(self.varying_packet_min_size + self.varying_packet_max_size) // 2]
        return []
