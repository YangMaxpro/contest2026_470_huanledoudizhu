/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XIAOPAI_WIFI_PROFILE_SERVICE_H
#define XIAOPAI_WIFI_PROFILE_SERVICE_H
#include <easyflash.h>
#include "bk7258_wifi_profile.h"

#define XIAOPAI_WIFI_ENV "xiaopai.wifi.v1"

static void xiaopai_profile_wipe(void *p, size_t n)
{
    volatile unsigned char *v = p;
    while (n--) *v++ = 0;
}

/* Executed on the serialized controller task, never an ISR. EasyFlash owns
 * its semaphore, CRC, update/GC protocol and the vendor Flash notification. */
static void xiaopai_profile_service(const void *data, size_t length,
                                    struct bk7258_wifi_profile_response *out)
{
    struct bk7258_wifi_profile_request req = {0};
    struct bk7258_wifi_profile saved = {0};
    size_t stored = 0;
    size_t got;
    memset(out, 0, sizeof(*out));
    out->status = BK7258_WIFI_PROFILE_INVALID;
    if (length != sizeof(req)) return;
    memcpy(&req, data, sizeof(req));
    if (req.operation > BK7258_WIFI_PROFILE_CLEAR) goto done;
    if (req.operation == BK7258_WIFI_PROFILE_SET)
    {
        if (!bk7258_wifi_profile_valid(&req.profile)) goto done;
    }
    else
    {
        /* GET/CLEAR must carry a zero profile, including future fields. */
        if (memcmp(&req.profile, &saved, sizeof(saved))) goto done;
    }

    got = ef_get_env_blob(XIAOPAI_WIFI_ENV, &saved, sizeof(saved), &stored);
    if (req.operation == BK7258_WIFI_PROFILE_GET)
    {
        if (got == 0 && stored == 0)
            out->status = BK7258_WIFI_PROFILE_MISSING;
        else if (got == sizeof(saved) && stored == sizeof(saved) &&
                 bk7258_wifi_profile_valid(&saved))
        {
            out->profile = saved;
            out->status = BK7258_WIFI_PROFILE_OK;
        }
        goto done;
    }
    out->status = BK7258_WIFI_PROFILE_IO;
    if (req.operation == BK7258_WIFI_PROFILE_CLEAR)
    {
        if (got == 0 && stored == 0)
        {
            out->status = BK7258_WIFI_PROFILE_OK;
            goto done;
        }
        if (ef_set_env_blob(XIAOPAI_WIFI_ENV, NULL, 0) != EF_NO_ERR)
            goto done;
        stored = 0;
        got = ef_get_env_blob(XIAOPAI_WIFI_ENV, &saved, sizeof(saved), &stored);
        if (got == 0 && stored == 0) out->status = BK7258_WIFI_PROFILE_OK;
        goto done;
    }
    if (got == sizeof(saved) && stored == sizeof(saved) &&
        !memcmp(&saved, &req.profile, sizeof(saved)))
    {
        out->status = BK7258_WIFI_PROFILE_OK;
        goto done;
    }
    if (ef_set_env_blob(XIAOPAI_WIFI_ENV, &req.profile,
                        sizeof(req.profile)) != EF_NO_ERR) goto done;
    memset(&saved, 0, sizeof(saved));
    stored = 0;
    got = ef_get_env_blob(XIAOPAI_WIFI_ENV, &saved, sizeof(saved), &stored);
    if (got == sizeof(saved) && stored == sizeof(saved) &&
        !memcmp(&saved, &req.profile, sizeof(saved)))
        out->status = BK7258_WIFI_PROFILE_OK;
done:
    xiaopai_profile_wipe(&req, sizeof(req));
    xiaopai_profile_wipe(&saved, sizeof(saved));
}
#endif
