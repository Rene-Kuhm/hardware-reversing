{
  description = "PC Monitor NixOS – HID display daemon for VID:3554 PID:FA09";

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
            version = "1.0.0";
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

            # ---- Max-value knobs (matching the original nud_Pic* controls) ----
            maxCpuTemp  = lib.mkOption { type = lib.types.float; default = 100.0;  description = "CPU temp scale max (°C)."; };
            maxCpuUsage = lib.mkOption { type = lib.types.float; default = 100.0;  description = "CPU usage scale max (%)."; };
            maxCpuPower = lib.mkOption { type = lib.types.float; default = 253.0;  description = "CPU power scale max (W)."; };
            maxCpuFreq  = lib.mkOption { type = lib.types.float; default = 5600.0; description = "CPU freq scale max (MHz)."; };
            maxCpuVolt  = lib.mkOption { type = lib.types.float; default = 1.5;    description = "CPU voltage scale max (V)."; };
            maxGpuTemp  = lib.mkOption { type = lib.types.float; default = 110.0;  description = "GPU temp scale max (°C)."; };
            maxGpuUsage = lib.mkOption { type = lib.types.float; default = 100.0;  description = "GPU usage scale max (%)."; };
            maxGpuPower = lib.mkOption { type = lib.types.float; default = 160.0;  description = "GPU power scale max (W)."; };
            maxGpuFreq  = lib.mkOption { type = lib.types.float; default = 2589.0; description = "GPU freq scale max (MHz)."; };
            maxWcFan    = lib.mkOption { type = lib.types.float; default = 3000.0; description = "Water-cooling fan RPM scale max."; };
            maxFan      = lib.mkOption { type = lib.types.float; default = 3000.0; description = "System fan RPM scale max."; };
          };

          # ----------------------------------------------------------------
          # Implementation
          # ----------------------------------------------------------------
          config = lib.mkIf cfg.enable {

            # -- udev rule: give the pc-monitor group rw access to the device --
            services.udev.extraRules = ''
              # PC Monitor USB HID display (VID:3554 PID:FA09)
              SUBSYSTEM=="hidraw", ATTRS{idVendor}=="3554", ATTRS{idProduct}=="fa09", \
                MODE="0660", GROUP="pc-monitor", TAG+="systemd"

              # Also match the parent USB device
              SUBSYSTEM=="usb", ATTRS{idVendor}=="3554", ATTRS{idProduct}=="fa09", \
                MODE="0660", GROUP="pc-monitor"
            '';

            # -- Dedicated system group so the daemon doesn't run as root -------
            users.groups.pc-monitor = {};

            # -- Allow the service user to read RAPL energy counters ------------
            # RAPL is readable by root by default; expose it via the service's
            # supplementary groups or via a udev rule for powercap.
            services.udev.extraRules = lib.mkAfter ''
              # RAPL powercap – allow pc-monitor group to read energy counters
              SUBSYSTEM=="powercap", ACTION=="add", \
                RUN+="${pkgs.coreutils}/bin/chmod g+r /sys%p/energy_uj", \
                RUN+="${pkgs.coreutils}/bin/chgrp pc-monitor /sys%p/energy_uj"
            '';

            # -- systemd service -----------------------------------------------
            systemd.services.pc-monitor = {
              description   = "PC Monitor HID display daemon";
              wantedBy      = [ "multi-user.target" ];
              after         = [ "systemd-udev-settle.service" "multi-user.target" ];
              # Restart automatically if the process exits
              serviceConfig = {
                ExecStart = lib.concatStringsSep " " (
                  [ "${monitorPackage}/bin/pc-monitor" ]
                  ++ [ "--log-level" cfg.logLevel ]
                  ++ lib.optionals cfg.verbose [ "--verbose" ]
                  ++ [
                    "--max-cpu-temp"  (toString cfg.maxCpuTemp)
                    "--max-cpu-usage" (toString cfg.maxCpuUsage)
                    "--max-cpu-power" (toString cfg.maxCpuPower)
                    "--max-cpu-freq"  (toString cfg.maxCpuFreq)
                    "--max-cpu-volt"  (toString cfg.maxCpuVolt)
                    "--max-gpu-temp"  (toString cfg.maxGpuTemp)
                    "--max-gpu-usage" (toString cfg.maxGpuUsage)
                    "--max-gpu-power" (toString cfg.maxGpuPower)
                    "--max-gpu-freq"  (toString cfg.maxGpuFreq)
                    "--max-wc-fan"    (toString cfg.maxWcFan)
                    "--max-fan"       (toString cfg.maxFan)
                  ]
                );

                Restart         = "on-failure";
                RestartSec      = "5s";

                # Run as a dedicated user with the pc-monitor group
                DynamicUser     = true;
                Group           = "pc-monitor";
                # Supplementary groups for sensor access
                SupplementaryGroups = [ "video" ];

                # -- Hardening --
                PrivateTmp          = true;
                ProtectSystem       = "strict";
                ProtectHome         = true;
                NoNewPrivileges     = true;
                # Allow reading hwmon / proc / sys
                ReadOnlyPaths       = [ "/sys" "/proc" ];
                # CAP_DAC_READ_SEARCH lets us read protected sysfs files (e.g. RAPL)
                # without running as root.  Drop everything else.
                CapabilityBoundingSet = [ "CAP_DAC_READ_SEARCH" ];
                AmbientCapabilities   = [ "CAP_DAC_READ_SEARCH" ];

                # Resource limits
                LimitNOFILE  = 256;
                Nice         = 10;
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
          version = "1.0.0";
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
