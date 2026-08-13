{
  description = "Stream Station NixOS — Mirabox Stream Dock daemon para NixOS";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        pythonEnv = pkgs.python311.withPackages (ps: with ps; [
          hid          # python-hidapi: acceso a dispositivos HID
          pillow       # procesamiento de imágenes para LCD
          websockets   # servidor WebSocket compatible Stream Deck SDK
        ]);

        streamStationPkg = pkgs.stdenv.mkDerivation {
          name    = "stream-station-nixos";
          version = "1.0.0";
          src     = ./.;

          buildInputs = [ pythonEnv pkgs.hidapi ];

          installPhase = ''
            mkdir -p $out/bin $out/share/stream-station
            cp stream_station.py $out/share/stream-station/

            makeWrapper ${pythonEnv}/bin/python3 $out/bin/stream-station \
              --add-flags "$out/share/stream-station/stream_station.py" \
              --prefix LD_LIBRARY_PATH : "${pkgs.hidapi}/lib"
          '';

          nativeBuildInputs = [ pkgs.makeWrapper ];
        };

      in {
        packages.default = streamStationPkg;

        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            pythonEnv
            hidapi
            usbutils    # lsusb
            usbhid-dump # usbhid-dump para análisis
          ];
          shellHook = ''
            echo "Stream Station NixOS dev shell"
            echo "Uso: python3 stream_station.py list"
            echo ""
            echo "Permisos requeridos:"
            echo "  sudo usermod -aG plugdev \$USER"
            echo "  # (o ejecutar con sudo para pruebas)"
          '';
        };

        apps.default = {
          type    = "app";
          program = "${streamStationPkg}/bin/stream-station";
        };
      }
    ) // {
      # NixOS module
      nixosModules.default = { config, lib, pkgs, ... }:
        let
          cfg = config.services.streamStation;
        in {
          options.services.streamStation = {
            enable = lib.mkEnableOption "Stream Station daemon para Mirabox Stream Dock";

            user = lib.mkOption {
              type    = lib.types.str;
              default = "stream-station";
              description = "Usuario bajo el que corre el daemon";
            };

            group = lib.mkOption {
              type    = lib.types.str;
              default = "plugdev";
              description = "Grupo con acceso a dispositivos HID";
            };

            configFile = lib.mkOption {
              type    = lib.types.path;
              default = "/etc/stream-station/config.toml";
              description = "Ruta al archivo de configuración TOML";
            };

            brightness = lib.mkOption {
              type    = lib.types.ints.between 0 100;
              default = 70;
              description = "Brillo inicial de pantalla (0-100)";
            };

            wsServer = lib.mkOption {
              type    = lib.types.bool;
              default = false;
              description = "Activar servidor WebSocket compatible Stream Deck SDK";
            };

            wsPort = lib.mkOption {
              type    = lib.types.port;
              default = 23519;
              description = "Puerto del servidor WebSocket";
            };

            logLevel = lib.mkOption {
              type    = lib.types.enum ["DEBUG" "INFO" "WARNING" "ERROR"];
              default = "INFO";
              description = "Nivel de log";
            };

            package = lib.mkOption {
              type    = lib.types.package;
              default = self.packages.${pkgs.system}.default;
              description = "Paquete stream-station-nixos a usar";
            };
          };

          config = lib.mkIf cfg.enable {
            # ── udev: permisos para el dispositivo ─────────────────────────
            services.udev.extraRules = ''
              # Mirabox Stream Dock (Stream Station)
              SUBSYSTEM=="hidraw", ATTRS{idVendor}=="3554", ATTRS{idProduct}=="fa09", \
                MODE="0660", GROUP="${cfg.group}", TAG+="uaccess"
              SUBSYSTEM=="usb", ATTRS{idVendor}=="3554", ATTRS{idProduct}=="fa09", \
                MODE="0660", GROUP="${cfg.group}", TAG+="uaccess"
            '';

            # ── Grupo plugdev ───────────────────────────────────────────────
            users.groups.plugdev = {};

            # ── Usuario del servicio ────────────────────────────────────────
            users.users = lib.mkIf (cfg.user == "stream-station") {
              stream-station = {
                isSystemUser = true;
                group        = cfg.group;
                description  = "Stream Station daemon user";
              };
            };

            # ── Config por defecto si no existe ────────────────────────────
            environment.etc."stream-station/config.toml" = lib.mkDefault {
              text = ''
                brightness = ${toString cfg.brightness}
                ws_server  = ${if cfg.wsServer then "true" else "false"}
                ws_port    = ${toString cfg.wsPort}
              '';
            };

            # ── Servicio systemd ────────────────────────────────────────────
            systemd.services.stream-station = {
              description = "Stream Station daemon (Mirabox Stream Dock)";
              wantedBy    = [ "multi-user.target" ];
              after       = [ "local-fs.target" "udev.service" ];

              serviceConfig = {
                ExecStart = lib.concatStringsSep " " ([
                  "${cfg.package}/bin/stream-station"
                  "--config" cfg.configFile
                  "--log-level" cfg.logLevel
                  "daemon"
                ] ++ lib.optionals cfg.wsServer [ "--ws" ]);

                User             = cfg.user;
                Group            = cfg.group;
                Restart          = "on-failure";
                RestartSec       = "5s";

                # Hardening
                NoNewPrivileges  = true;
                PrivateTmp       = true;
                ProtectSystem    = "strict";
                ProtectHome      = "read-only";
                ReadWritePaths   = [
                  "/run/stream-station"
                  "/var/log"
                  "/tmp"
                ];

                # Acceso a dispositivos USB/HID
                SupplementaryGroups = [ cfg.group ];
                DeviceAllow  = [
                  "char-usb_device rw"
                  "char-hidraw rw"
                ];
                DevicePolicy = "closed";

                # Capacidades mínimas
                AmbientCapabilities  = [];
                CapabilityBoundingSet = [];
              };

              environment = {
                STREAM_STATION_CONFIG = cfg.configFile;
              };
            };
          };
        };
    };
}
