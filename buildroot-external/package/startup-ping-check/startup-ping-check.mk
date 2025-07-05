################################################################################
# Startup ping check package
################################################################################

STARTUP_PING_CHECK_VERSION = 1.0
STARTUP_PING_CHECK_SITE = $(BR2_EXTERNAL_BR2RAUC_PATH)/package/startup-ping-check
STARTUP_PING_CHECK_SITE_METHOD = local
STARTUP_PING_CHECK_LICENSE = MIT

# Nothing to compile, just install script

define STARTUP_PING_CHECK_INSTALL_INIT_SYSV
	$(INSTALL) -m 0755 -D $(STARTUP_PING_CHECK_SITE)/S02pingcheck \
		$(TARGET_DIR)/etc/init.d/S02pingcheck
endef

$(eval $(generic-package))
