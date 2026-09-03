# Changing the FlowTrack data location

Settings > Data Location offers two deliberately separate operations:

- **Move my current FlowTrack data** creates and validates a safety backup, then
  closes the active dataset and safely copies it to the selected folder. Despite
  the user-facing name, the original is retained as a recovery copy.
- **Use an existing FlowTrack data folder** checks an existing `flowtrack.db`
  read-only before selecting it. The selected database is not initialised,
  migrated, leased, merged, or otherwise modified during selection.

A move copies the durable database, managed backups, and the reserved
`attachments/` directory when present. Session leases, SQLite journal/WAL
sidecars, temporary files, and synchronisation conflict copies are not copied as
durable ownership state. Copying uses a staging directory and the new database is
checked for SQLite integrity and a readable FlowTrack migration revision before
the application setting is changed.

Both operations take effect after a clean shutdown and restart. Normal FlowTrack
startup remains authoritative for the new location, including conflict checks,
the process lock, session lease decisions, integrity checks, migrations, backup
policy, and journal configuration.

Local folders and user-managed synchronised folders such as OneDrive are
supported, but synchronisation is not database replication. Close FlowTrack on
one computer before opening the same data on another, allow synchronisation to
finish, and follow any startup safety warning. FlowTrack never automatically
merges SQLite databases or deletes the previous dataset.
