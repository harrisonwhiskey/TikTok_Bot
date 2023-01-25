Java.perform(function () {
    var HashMapNode = Java.use('java.util.HashMap$Node');
    var google_aid = null;
    var openudid = null;
    var uuid = null;
    var data = null;

    // google_aid
    var v = Java.use('com.google.android.gms.ads.b.a$a')
	v.$init.implementation = function(aid, var2){
        if (google_aid == null) {
            send('google_aid')
            var op = recv('input', function (value) {
                google_aid = value.payload.toString()
            })
            op.wait()
        }
        // console.log('\n**js google_aid: ' + google_aid);
		this.$init(google_aid, var2)
	}
    
    // openudid
	var v = Java.use('com.ss.android.deviceregister.c.c')
	v.a.overload('android.content.Context').implementation = function(a) {
        if (openudid == null) {
            send('openudid')
            var op = recv('input', function (value) {
                openudid = value.payload.toString()
            })
            op.wait()
        }
        // console.log('\n**js openudid: ' + openudid);
		return openudid
    }

    // uuid
    var v = Java.use('com.bytedance.ies.ugc.statisticlogger.config.a')
	v.h.implementation = function() {
        if (uuid == null) {
            // console.log('\n**js uuid: ' + uuid);
            send('uuid')
            var op = recv('input', function (value) {
                uuid = value.payload.toString()
            })
            op.wait()
        }
        // console.log('\n**js uuid: ' + uuid);
		return uuid
	}

    // get device_id / install_id
    var v = Java.use('com.ss.android.deviceregister.b.b$a')
    v.a.overload("org.json.JSONObject").implementation = function (a) {
        console.log('\n**js device_id / install_id: ' + a);
        send(a.toString());
        return this.a(a)
    }

    // device_registration body payload
	// v.a.overload('java.lang.String', 'int').implementation = function (device_str, b) {
    //     console.log('js: ' + device_str)
    //     return this.a(device_str, b)
    // }

	v.b.overload('java.lang.String', 'int').implementation = function (device_str, b) {
        device_str = JSON.parse(device_str)
        if (data == null) {
            send('data')
            var op = recv('input', function (value) {
                data = JSON.parse(value.payload.toString())
            })
            op.wait()
        }
        device_str['header']['os_version'] = data['os_version']
        device_str['header']['os_api'] = data['os_api']
        device_str['header']['device_model'] = data['model']
        device_str['header']['device_brand'] = data['brand']
        device_str['header']['cpu_abi'] = data['cpu_abi']
        device_str['header']['density_dpi'] = data['dpi']
        device_str['header']['resolution'] = data['resolution']
        device_str['header']['carrier'] = 'Megafon'
        device_str['header']['mcc_mnc'] = '25002'
        device_str['header']['rom_version'] = data['rom_version']
        device_str['header']['region'] = 'ru'
        device_str['header']['tz_name'] = 'Russia/Moscow'
        // console.log('js: ' + device_str + ' header: ' + data['header'])
        return this.b(JSON.stringify(device_str), b)
    }


    // api url paramters
	var v = Java.use('com.ss.android.common.applog.NetUtil')
	v.putCommonParams.implementation = function (a, b) {
        if (data == null) {
            send('data')
            var op = recv('input', function (value) {
                data = JSON.parse(value.payload.toString())
            })
            op.wait()
        }
        this.putCommonParams(a, b)
        
        a.put('device_type', data['model']);
        a.put('device_brand', data['brand']);
        a.put('resolution', data['resolution']);
        a.put('os_version', data['os_version']);
        a.put('timezone_name', 'Russia/Moscow');
		a.put('carrier_region_v2', '250');
		a.put('sys_region', 'ru');
		a.put('region', 'ru');
		a.put('dpi', data['dpi']);
		a.put('mcc_mnc', '25002');
		a.put('uuid', data['uuid']);

		var res = '**start-1** '
		var iterator = a.entrySet().iterator();
		while (iterator.hasNext()) {
		  var entry = Java.cast(iterator.next(), HashMapNode);
		  res = res + entry.getKey() + " : " + entry.getValue() + ', ';
		}
		res = res + ' **end-1\n'
		// console.log(res)
    }

})