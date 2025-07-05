################################################################################
# Startup ping check package
################################################################################

STARTUP_PING_CHECK_VERSION = 1.0
STARTUP_PING_CHECK_SITE = $(BR2_EXTERNAL_BR2RAUC_PATH)/package/startup-ping-check
STARTUP_PING_CHECK_SITE_METHOD = local
STARTUP_PING_CHECK_LICENSE = MIT

# Nothing to compile, just install script and unit

# Install script for both init systems

define STARTUP_PING_CHECK_INSTALL_TARGET_CMDS
	$(INSTALL) -m 0755 -D $(STARTUP_PING_CHECK_SITE)/pingcheck.sh \
		$(TARGET_DIR)/usr/bin/pingcheck.sh
endef

# SysV init fallback

define STARTUP_PING_CHECK_INSTALL_INIT_SYSV
	$(INSTALL) -m 0755 -D $(STARTUP_PING_CHECK_SITE)/S02pingcheck \
		$(TARGET_DIR)/etc/init.d/S02pingcheck
endef

# systemd service

define STARTUP_PING_CHECK_INSTALL_INIT_SYSTEMD
	$(INSTALL) -m 0644 -D $(STARTUP_PING_CHECK_SITE)/startup-ping-check.service \
		$(TARGET_DIR)/etc/systemd/system/startup-ping-check.service
endef

$(eval $(generic-package))
