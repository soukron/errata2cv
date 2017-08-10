# errata2cv
`errata2cv`is a python script to update your Content Views by injecting erratas, propagate them
to affected Composite Content Views and/or update hosts	where the erratas are
applicable.

If you want a more complex handling of your Content Views there are other options to consider like
[cvmanager](https://github.com/RedHatSatellite/katello-cvmanager) and/or [katello-publish-cv](https://github.com/RedHatSatellite/katello-publish-cvs) but that tools publish new Content View versions everytime, which may be overkill in some situations.

Note: It only updates Content Views in _Library_ lifecycle environment. See **Examples** below for an example Content View organization.

## Features
* Update Content Views using incremental versions.
* Add erratas by filtering their type, severity and date.
* Propagate erratas to Composite Content Views.
* Apply erratas to hosts if applicable using Remote Execution job (this allows to re-run the job in hosts where it failed for any reason).
* Import as a Job Template to schedule it easily.

## Compatibility
Tested and works on: 
* Satellite 6.2.10 in RHEL 7.3 (python 2.7.5) 

## Instructions
Use command help to understand the arguments:

~~~
usage: errata2cv.py [-h] --cv CV [--type TYPE] [--severity SEVERITY]
                    [--from-date FROM_DATE] [--to-date TO_DATE] [--propagate]
                    [--update-hosts UPDATE_HOSTS] [--dry-run] [-v]

Satellite 6 - Content View Errata Updater v1.1.0

optional arguments:
  -h, --help            show this help message and exit
  --cv CV               Comma-separated list of Content View names to update.
  --type TYPE           Comma-separated list of errata types to include
                        (bugfix, enhancement or security). Default: Security.
  --severity SEVERITY   Comma-separated list of errata severity level to
                        include (critical, important, moderate or low).
                        Default: Critical.
  --from-date FROM_DATE
                        Date to use as a referente instead of Content View
                        publishing date (YYYY/MM/DD).
  --to-date TO_DATE     Date to use as a referente to stop including erratas
                        (YYYY/MM/DD).
  --propagate           Propagate incremental version to Composite Content
                        Views. Default: False.
  --update-hosts UPDATE_HOSTS
                        Comma-separated list of lifecycle environments to
                        update hosts with the included erratas.
  --dry-run             Check for erratas but don't update Content Views nor
                        update hosts.
  -d, --debug           Show debug information (including GET/POST requests)
  -V, --version         show program's version number and exit
~~~

## Examples
### Scenario
`errata2cv` is specially useful where Composite Content Views are used and erratas must be updated frequently from base Content Views without updating other packages.

Here is a sample Content View organization:
  * **cv-rhel73-rpms**: simple Content View with RHEL 7.3 and Satellite 6.2 tools repositories. Their versions only promote to _Library_.
  * **cv-rhel7-eap7-rpms**: simple Content View with EAP for RHEL 7 repositories. Their versions only promote to _Library_.
  * **cv-rhel7-custom-rpms**: simple Content View with custom software for RHEL 7 repositories. Their versions only promote to _Library_.
  * **ccv-rhel73-server**: Composite Content View with RHEL 7.3, EAP7 and Custom software Content Views. 
    * Their version promote through a _DEV_ --> _INT_ --> _PRE_ --> _PRO_ path.

### Examples
These a different example situations you can resolve with `errata2cv`:
* Update RHEL 7.3 Content View with Security - Critical erratas since its last publishing date:
  ~~~
  ./errata2cv.py --cv cv-rhel73-rpms
  ~~~
* Update RHEL 7.3 Content View with any Critical errata since its last publishing date and propagate to Composite Content View:
   ~~~
  ./errata2cv.py --cv cv-rhel73-rpms \
                  --type bugfix,security,enhacement \
                  --propagate
  ~~~
* Update RHEL 7.3 and EAP7 Content Views with any Security errata published since January 1st, 2017:
  ~~~
  ./errata2cv.py --cv cv-rhel73-rpms,cv-rhel7-eap7-rpms \
                 --severity none,low,moderate,important,critical \
                 --from-date 2017/01/01
  ~~~
* Update RHEL 7.3 Content View with any Security errata published since January 1st and update any host in _DEV_, _INT_ and _PRE_ lifecycle environment:
  ~~~
  ./errata2cv.py --cv cv-rhel73-rpms \
                 --severity none,low,moderate,important,critical \
                 --from-date 2017/01/01 \
                 --propagate \
                 --update-hosts DEV,INT,PRE
  ~~~

## TODO
* Improve error handling.
* Allow updating Content Views in other environments different from _Library_.
* Create aliases for type and/or severity groups like "**any**" which contains all posible values.

## Contact
Reach me in [Twitter](http://twitter.com/soukron) or email in soukron at gmbros.net

