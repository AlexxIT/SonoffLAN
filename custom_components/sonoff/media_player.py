from homeassistant.components.media_player import (
    BrowseMedia,
    MediaClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.components.media_source import BrowseMediaSource
from homeassistant.components import media_source
from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import SIGNAL_ADD_ENTITIES, XRegistry

PARALLEL_UPDATES = 0  # fix entity_platform parallel_updates Semaphore


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES,
        lambda x: add_entities([e for e in x if isinstance(e, MediaPlayerEntity)]),
    )


class XPanelBuzzer(XEntity, MediaPlayerEntity):
    param = "buzzerAlarm"
    uid = "buzzer"

    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.BROWSE_MEDIA
    )
    _attr_volume_level = 1.0

    def set_state(self, params: dict):
        if v := params.get(self.param):
            if name := v.get("fileName"):
                self._attr_state = MediaPlayerState.PLAYING
                self._attr_media_content_id = name
            if volume := v.get("volume"):
                self._attr_volume_level = volume / 100
            if v.get("mode") == "stop":
                self._attr_state = MediaPlayerState.IDLE

    async def async_set_volume_level(self, volume: float) -> None:
        self._attr_volume_level = volume
        self.async_write_ha_state()

    async def async_browse_media(
        self,
        media_content_type: str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        childrens = []
        for key in ("alarm", "alert", "ring"):
            for i in range(1, 6):
                item = BrowseMediaSource(
                    title=f"{key.title()} Sound {i}",
                    domain="ring",
                    identifier=f"{key}{i}.mp3",
                    media_class=MediaClass.APP,
                    media_content_type=MediaClass.APP,
                    can_play=True,
                    can_expand=False,
                )
                childrens.append(item)

        return BrowseMediaSource(
            title=self.name,
            children=childrens,
            domain=None,
            identifier=None,
            media_class=None,
            media_content_type=None,
            can_play=False,
            can_expand=True,
        )

    async def async_play_media(self, media_type: str, media_id: str, **kwargs) -> None:
        # {'buzzerAlarm': {'test': True, 'fileName': 'ring/ring5.mp3', 'volume': 66, 'duration': 2}}
        if media_source.is_media_source_id(media_id):
            media_id = media_id[len(media_source.URI_SCHEME) :]

        extra = kwargs["extra"]
        params = {
            "test": True,
            "fileName": media_id,
            "volume": int(extra.get("volume", self.volume_level) * 100),
            "duration": extra.get("duration", 2),
        }
        await self.ewelink.send(self.device, {self.param: params})
