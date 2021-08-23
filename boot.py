import storage
# mount storage r/w for autoupdater
storage.remount("/", False)
