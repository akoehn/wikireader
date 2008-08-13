/*
    e07 bootloader suite
    Copyright (c) 2008 Daniel Mack <daniel@caiaq.de>

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
*/

#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <fcntl.h>
#include <errno.h>
#include <string.h>

#include "e07.h"
#include "misc.h"

int sync_cpu(int fd)
{
	const unsigned char syncbytes[] = { 0x80, 0x80, 0x80, 0x80 };
	unsigned char buf[4];

	msg("sending sync bytes ... ");
	write(fd, syncbytes, sizeof(syncbytes));
	msg("done.\n");

	read(fd, buf, 4);
	msg("reading CPU id: %02x%02x%02x%02x\n", buf[0], buf[1], buf[2], buf[3]);

	if (buf[0] != 0x06 || buf[1] != 0x0e || buf[2] != 0x07 || buf[3] != 0x00) {
		error("invalid  CPU id! Bummer.\n");
		return -1;
	}

	return 0;
}

int bootstrap(int ttyfd, const char *bootstrap_file)
{
	char bootstrap_buf[512], verify_buf[512];
	int fd = open(bootstrap_file, O_RDONLY);
	
	memset(bootstrap_buf, 0, sizeof(bootstrap_buf));
	memset(verify_buf, 0, sizeof(verify_buf));
	
	if (fd < 0) {
		error("unable to open bootstrap file %s: %s\n", bootstrap_file, strerror(errno));
		return fd;
	}

	read(fd, bootstrap_buf, sizeof(bootstrap_buf));
	close(fd);

	msg("uploading %d bytes of bootstrap code from file >%s< ... ", sizeof(bootstrap_buf), bootstrap_file);
	write(ttyfd, bootstrap_buf, sizeof(bootstrap_buf));
	msg("done.\n");

	msg("reading back bootstrap code ... ");
	read_blocking(ttyfd, verify_buf, sizeof(verify_buf));
	if (memcmp(bootstrap_buf, verify_buf, sizeof(bootstrap_buf)) != 0) {
		error("FAILED to verify bootstrap code!\n");
		return -1;
	}

	msg("ok.\n");
	return 0;
}

