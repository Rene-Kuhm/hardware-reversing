{
  description = "PC Monitor NixOS – HID display daemon for VID:5131 PID:2007";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    let
      # -----------------------------------------------------------------------
      # NixOS module (imported by your system configuration)
      # -----------------------------------------------------------------------
      nixosModule = { config, lib, pkgs, ... }:
        let
          cfg = config.services.pcMonitor;

          # Build the Python environment with the hid library
          pythonEnv = pkgs.python3.withPackages (ps: [
            ps.hid    # hidapi Python bindings (pip name: hid)
          ]);

          # The monitor script is installed as a proper package
          monitorPackage = pkgs.stdenv.mkDerivation {
            pname   = "pc-monitor";
            version = "2.0.0";
            src     = ./.;

            buildInputs = [ pythonEnv ];
            nativeBuildInputs = [ pkgs.makeWrapper ];

            installPhase = ''
              install -Dm755 monitor.py $out/lib/pc-monitor/monitor.py

              makeWrapper ${pythonEnv}/bin/python $out/bin/pc-monitor \
                --add-flags "$out/lib/pc-monitor/monitor.py" \
                --prefix PATH : ${lib.makeBinPath [ pkgs.kmod ]}
            '';

            meta = {
              description = "PC Monitor HID display daemon";
              license     = lib.licenses.mit;
              platforms   = lib.platforms.linux;
            };
          };

        in
        {
          # ----------------------------------------------------------------
          # Options
          # ----------------------------------------------------------------
          options.services.pcMonitor = {
            enable = lib.mkEnableOption "PC Monitor HID display daemon";

            logLevel = lib.mkOption {
              type    = lib.types.enum [ "DEBUG" "INFO" "WARNING" "ERROR" ];
              default = "INFO";
              description = "Logging verbosity.";
            };

            verbose = lib.mkOption {
              type    = lib.types.bool;
              default = false;
              description = "Log sensor values every cycle (sets log level to DEBUG).";
            };
          };

          # ----------------------------------------------------------------
          # Implementation
          # ----------------------------------------------------------------
          config = lib.mkIf cfg.enable {

            # -- udev rules: HID device access + RAPL powercap --
            services.udev.extraRules = ''
              # PC Monitor USB HID display (VID:5131 PID:2007)
              SUBSYSTEM=="hidraw", ATTRS{idVendor}=="5131", ATTRS{idProduct}=="2007", \
                MODE="0660", GROUP="pc-monitor", TAG+="systemd"

              # Also match the parent USB device
              SUBSYSTEM=="usb", ATTRS{idVendor}=="5131", ATTRS{idProduct}=="2007", \
                MODE="0660", GROUP="pc-monitor"

              # RAPL powercap – allow pc-monitor group to read energy counters
              SUBSYSTEM=="powercap", ACTION=="add", \
                RUN+="${pkgs.coreutils}/bin/chmod g+r /sys%p/energy_uj", \
                RUN+="${pkgs.coreutils}/bin/chgrp pc-monitor /sys%p/energy_uj"
            '';

            # -- Static user and group for the daemon ---------------------------
            users.groups.pc-monitor = {};
            users.users.pc-monitor = {
              isSystemUser = true;
              group        = "pc-monitor";
              extraGroups  = [ "video" ];
              description  = "PC Monitor daemon user";
            };

            # -- systemd service -----------------------------------------------
            systemd.services.pc-monitor = {
              description   = "PC Monitor HID display daemon";
              wantedBy      = [ "multi-user.target" ];
              after         = [ "systemd-udev-settle.service" "multi-user.target" ];
              serviceConfig = {
                ExecStart = lib.concatStringsSep " " (
                  [ "${monitorPackage}/bin/pc-monitor" ]
                  ++ [ "--log-level" cfg.logLevel ]
                  ++ lib.optionals cfg.verbose [ "--verbose" ]
                );

                Restart    = "on-failure";
                RestartSec = "5s";

                User  = "pc-monitor";
                Group = "pc-monitor";

                # -- Hardening --
                PrivateTmp          = true;
                ProtectSystem       = "strict";
                ProtectHome         = true;
                NoNewPrivileges     = true;
                ReadOnlyPaths       = [ "/sys" "/proc" ];
                CapabilityBoundingSet = [ "CAP_DAC_READ_SEARCH" ];
                AmbientCapabilities   = [ "CAP_DAC_READ_SEARCH" ];

                LimitNOFILE = 256;
                Nice        = 10;
              };
            };

            # -- Make lm_sensors available (for sensor discovery/debugging) -----
            environment.systemPackages = [ pkgs.lm_sensors ];
          };
        };

    in
    {
      # Export the NixOS module
      nixosModules.default    = nixosModule;
      nixosModules.pcMonitor  = nixosModule;  # named alias

      # Per-system outputs (dev shell, package)
    } // flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };

        pythonEnv = pkgs.python3.withPackages (ps: [
          ps.hid
        ]);

        monitorPackage = pkgs.stdenv.mkDerivation {
          pname   = "pc-monitor";
          version = "2.0.0";
          src     = ./.;

          buildInputs    = [ pythonEnv ];
          nativeBuildInputs = [ pkgs.makeWrapper ];

          installPhase = ''
            install -Dm755 monitor.py $out/lib/pc-monitor/monitor.py
            makeWrapper ${pythonEnv}/bin/python $out/bin/pc-monitor \
              --add-flags "$out/lib/pc-monitor/monitor.py"
          '';

          meta = with pkgs.lib; {
            description = "PC Monitor HID display daemon";
            license     = licenses.mit;
            platforms   = platforms.linux;
          };
        };

      in
      {
        # Build the package:  nix build
        packages.default    = monitorPackage;
        packages.pc-monitor = monitorPackage;

        # Development shell:  nix develop
        devShells.default = pkgs.mkShell {
          buildInputs = [
            pythonEnv
            pkgs.lm_sensors
            pkgs.hidapi       # C library (needed by the hid Python package at runtime)
            pkgs.python3Packages.pip
          ];

          shellHook = ''
            echo "PC Monitor dev shell ready."
            echo "  Run:  python monitor.py --dry-run --verbose"
            echo "  Test: python monitor.py --dry-run --log-level DEBUG"
          '';
        };

        # Run directly:  nix run
        apps.default = {
          type    = "app";
          program = "${monitorPackage}/bin/pc-monitor";
        };
      }
    );
}
