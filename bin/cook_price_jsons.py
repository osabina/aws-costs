#!/usr/bin/env python

# Helper script to cook the json data from amazon into
# something more easily usable (to us).

import json
import sys
import os


VAL_RATE_XLATE = {'perGBmoProvStorage' : ('monthly', 'gb'),
                  'perMMIOreq' : ('monthly', 'MIOR'), # million IO requests
                  'perPIOPSreq' : ('monthly', 'piops'),
                  'perGBmoDataStored' : ('monthly', 'gb'),}

VAL_NAME_XLATE = {'yrTerm1' : ('upfront', '1y'),
                  'yrTerm3' : ('upfront', '3y'),
                  'yrTerm1Hourly' : ('hourly', '1y'),
                  'yrTerm3Hourly' : ('hourly', '3y'),
                  'ebsOptimized' : ('hourly', 'eo'),}

STOR_TYPE_XLATE = {'storage' : ('monthly', 'S3'),
                   'reducedRedundancyStorage' : ('monthly', 'RRS'),
                   'glacierStorage' : ('monthly', 'glacier'),}

EBS_TYPE_XLATE = {'ebsVols' : 'standard',
                  'ebsPIOPSVols' : 'io1',
                  'ebsSnapsToS3' : 's3-snap',}

STOR_NAME_XLATE = {'firstTBstorage' : '1TB',
                   'next49TBstorage' : '50TB',
                   'next450TBstorage' : '500TB',
                   'next500TBstorage' : '1000TB',
                   'next4000TBstorage' : '5000TB',
                   'over5000TBstorage' : '>5000TB',}

INST_SIZE_XLATE = { 'u' : 'micro',
                    'sm' : 'small',
                    'med' : 'medium',
                    'lg' : 'large',
                    'xl' : 'xlarge',
                    'xxl' : '2xlarge',
                    'xxxxl' : '4xlarge',
                    'xxxxxxxxl' : '8xlarge',}

INST_TYPE_XLATE = { 'uResI' : 't1',
                    'uODI' : 't1',
                    'std' : 'm1',
                    'stdResI' : 'm1',
                    'stdODI' : 'm1',
                    'secgenstd' : 'm3',
                    'secgenstdResI' : 'm3',
                    'secgenstdODI' : 'm3',
                    'hiMemResI' : 'm2',
                    'hiMemODI' : 'm2',
                    'hiMem' : 'm2',
                    'hiCPU' : 'c1',
                    'hiCPUResI' : 'c1',
                    'hiCPUODI' : 'c1',
                    'clusterCompResI' : 'cc1', #SPECIAL CASE! 4xl is cc1 &
                    'clusterComputeI' : 'cc1', #SPECIAL CASE! 8xl is cc2
                    'clusterHiMemResI' : 'cr1',
                    'clusterHiMemODI' : 'cr1',
                    'clusterGPUResI' : 'cg1',
                    'clusterGPUI' : 'cg1',
                    'hiIo' : 'hi1',
                    'hiIoResI' : 'hi1',
                    'hiIoODI' : 'hi1',
                    'hiStoreResI' : 'hs1',
                    'hiStoreODI' : 'hs1',}

REGION_FIXUPS = { 'us-west' : 'us-west-1',
                  'us-east' : 'us-east-1',
                  'eu-ireland' : 'eu-west-1',
                  'apac-sin' : 'ap-southeast-1', 
                  'apac-tokyo' : 'ap-northeast-1', 
                  'apac-syd' : 'ap-southeast-2',} 

INST_DATA = {'ri-heavy-linux.json': 'Heavy Utilization',
             'ri-medium-linux.json': 'Medium Utilization',
             'ri-light-linux.json': 'Light Utilization',
             'pricing-on-demand-instances.json': 'On Demand',
             'pricing-ebs-optimized-instances.json': 'EBS Optimized',}

EBS_DATA = 'pricing-ebs.json'

S3_DATA = 'pricing-storage.json'

JSON_OUTFILE = 'aws-costs.json'


def fixup_region(r):
    # They are inconsistent with naming, which doesn't work so well for us.
    if r in REGION_FIXUPS:
        return REGION_FIXUPS[r]

    return r


def inst_name(ntype, nsize):
    name = '%s.%s' % (INST_TYPE_XLATE[ntype], INST_SIZE_XLATE[nsize])
    if name == 'cc1.8xlarge':
        name = 'cc2.8xlarge' # see above
    return name


def ebs_name(name):
    # Ok, this is silly, but I left it abstracted for consistency
    return EBS_TYPE_XLATE[name]


def s3_name(name):
    # Ok, this is silly, but I left it abstracted for consistency
    return STOR_NAME_XLATE[name]


def parse_inst_vals(vals, instance_class):
    if "Demand" in instance_class:
        # For on demand, input looks like:
        # {u'name': u'linux', u'prices': {u'USD': u'0.130'}},
        # {u'name': u'mswin', u'prices': {u'USD': u'0.230'}}  # Do not care
        if vals['name'] != 'linux':
            return(None, None)
        else:
            price = vals['prices']['USD']
            return('od', {'hourly' : price})
    else:
        # For reserved, input looks like:
        # {u'name': u'yrTerm1Hourly',
        #  u'prices': {u'USD': u'0.016'},
        #  u'rate': u'perhr'}   # rate is optional and we ignore it
        (ctype, cterm) = VAL_NAME_XLATE[vals['name']]
        price = vals['prices']['USD']
        return(cterm, {ctype : price})

def parse_ebs_vals(vals):
    # All look like:
    # {"prices": {"USD": "0.095"}, 
    #  "rate": "perGBmoDataStored"}
    (ctype, cterm) = VAL_RATE_XLATE[vals['rate']]
    price = vals['prices']['USD']
    return(cterm, {ctype : price})

def parse_s3_vals(vals):
    # All look like:
    # {"prices": { "USD": "0.095" },"type": "storage" },
    # {"prices": { "USD": "0.076" },"type": "reducedRedundancyStorage"},
    (ctype, cterm) = STOR_TYPE_XLATE[vals['type']]
    price = vals['prices']['USD']
    return(cterm, {ctype : price})

def parse_instance_data(mydict, filename, instance_class):
    with open(filename) as fp:
        jblob = fp.read()

    j = json.loads(jblob)

    for rdata in j['config']['regions']:
        region = fixup_region(rdata['region'])
        if region not in mydict:
            mydict[region] = {}

        for idict in rdata['instanceTypes']:
            itype = idict['type']

            for sdict in idict['sizes']:
                iname = inst_name(itype, sdict['size'])
                if iname not in mydict[region]:
                    mydict[region][iname] = {instance_class:{}}
                else:
                    mydict[region][iname][instance_class] = {}

                for vals in sdict['valueColumns']:
                    (term, cdict) = parse_inst_vals(vals, instance_class)
                    if term is None or cdict is None:  # Skippable
                        continue
                    ic_dict = mydict[region][iname][instance_class]
                    if term in ic_dict:
                        ic_dict[term].update(cdict)
                    else:
                        ic_dict[term] = cdict

def parse_s3_data(mydict, filename):
    with open(filename) as fp:
        jblob = fp.read()
        j = json.loads(jblob)

    for rdata in j['config']['regions']:
        region = fixup_region(rdata['region'])
        if region not in mydict:
            mydict[region] = {}

        for sdict in rdata['tiers']:
            sname = s3_name(sdict['name'])
            if sname not in mydict[region]:
                mydict[region][sname] = {}

                for vals in sdict['storageTypes']:
                    (term, cdict) = parse_s3_vals(vals)
                    if term is None or cdict is None:  # Skippable
                        continue
                    sc_dict = mydict[region][sname]
                    if term in sc_dict:
                        sc_dict[term].update(cdict)
                    else:
                        sc_dict[term] = cdict


def parse_ebs_data(mydict, filename):
    with open(filename) as fp:
        jblob = fp.read()

    j = json.loads(jblob)

    for rdata in j['config']['regions']:
        region = fixup_region(rdata['region'])
        if region not in mydict:
            mydict[region] = {}

        for edict in rdata['types']:
            ename = ebs_name(edict['name'])
            if ename not in mydict[region]:
                mydict[region][ename] = {}
            for vals in edict['values']:
                (term, cdict) = parse_ebs_vals(vals)
                if term is None or cdict is None:  # Skippable
                    continue
                ec_dict = mydict[region][ename]
                if term in ec_dict:
                    ec_dict[term].update(cdict)
                else:
                    ec_dict[term] = cdict


def main(args):
    if args:
        mypath = args[0]
    else:
        mypath = '.'
    
    # EC2
    cost_dict = {'instances' : {}}
    for (filename, inst_class) in INST_DATA.iteritems():
        parse_instance_data(cost_dict['instances'], os.path.join(mypath,
                            filename), inst_class)

    # EBS
    cost_dict['EBS'] = {}
    parse_ebs_data(cost_dict['EBS'], os.path.join(mypath, EBS_DATA))

    # S3
    cost_dict['S3'] = {}
    parse_s3_data(cost_dict['S3'],  os.path.join(mypath, S3_DATA))
    # etc., etc.

    # Save it out
    with open(os.path.join(mypath, JSON_OUTFILE), 'w') as fp:
        json.dump(cost_dict, fp)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
