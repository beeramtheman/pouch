#!/usr/bin/env python2.7

from configparser import SafeConfigParser
import sys
import boto.sqs
import boto.s3.connection
import boto.ec2
import boto.sqs
from time import sleep
import subprocess

config = SafeConfigParser()
config.read('config.ini')

def fill_config():
    print('Prompting to set unset options in config.ini.')
    print('If unsure about an option, see the comment above it in config.ini.')
    print('You can fill out config.ini to not have to do this.')

    for section in config.sections():
        for option in config.options(section):
            if not config.get(section, option):
                val = raw_input(section + ' - ' + option + ': ')
                config.set(section, option, val)

    print('All options set.')

class Job:
    def confirm_s3(self):
        conn = boto.s3.connection.S3Connection(
            config.get('aws', 'access_key_id'),
            config.get('aws', 'secret_access_key'))

        if conn.lookup(config.get('s3', 'results_bucket')):
            print('Bucket exists, continuing.')

        else:
            print("WARNING: AWS says your configured S3 bucket DOESN'T EXIST.")
            print('If your bucket name has periods this may be a false alarm.')
            print('If it does not exist your results will not be uploaded.')
            print('You can still access them in each EC2 instance created.')

    def setup_sqs(self):
        print('Connecting to SQS.')

        conn = boto.sqs.connect_to_region(
            config.get('aws', 'region'),
            aws_access_key_id=config.get('aws', 'access_key_id'),
            aws_secret_access_key=config.get('aws', 'secret_access_key'))

        if conn.get_queue(config.get('sqs', 'queue')):
            print('Error: queue already exists. Exiting.')
            sys.exit(1)

        print('Creating SQS queue.')
        queue = conn.create_queue(config.get('sqs', 'queue'), 15 * 60)
        print('Writing WAT paths to SQS queue.')

        with open(config.get('sqs', 'path_file')) as pf:
            capped = pf.readlines()[:int(config.get('sqs', 'path_cap'))]

            for paths in [capped[x:x+10] for x in xrange(0, len(capped), 10)]:
                queue.write_batch([(i, m, 0) for i, m in enumerate(paths)])

        self.queue_url = queue.url

    def setup_ec2_workers(self):
        print('Connecting to EC2.')

        conn = boto.ec2.connect_to_region(
            config.get('aws', 'region'),
            aws_access_key_id=config.get('aws', 'access_key_id'),
            aws_secret_access_key=config.get('aws', 'secret_access_key'))

        print('Running EC2 instances.')
        bdt = boto.ec2.blockdevicemapping.EBSBlockDeviceType()
        bdt.size = config.get('ec2', 'volume_size')
        bdt.delete_on_termination = True
        bdm = boto.ec2.blockdevicemapping.BlockDeviceMapping()
        bdm[config.get('ec2', 'volume_device')] = bdt

        self.reser = conn.run_instances(
            config.get('ec2', 'ami'),
            instance_type=config.get('ec2', 'type'),
            min_count=config.get('ec2', 'instances'),
            max_count=config.get('ec2', 'instances'),
            block_device_map = bdm,
            key_name=config.get('ec2', 'key_name'),
            security_groups=[config.get('ec2', 'security_group')])

    def wait_until_running(self):
        print('Waiting for EC2 instances to be running (patience).')

        # fixes bug where instances "do not exist" at first
        sleep(5)

        while False in [x.update() == 'running' for x in self.reser.instances]:
            sleep(1)

        # buggy period where "running" server isn't fully capabale (eg no SSH)
        print('Sleeping for a minute to ensure instances fully capable.')
        sleep(60)

    def run_scripts(self):
        print('Copying local scripts to remote instances.')

        for instance in self.reser.instances:
            subprocess.check_call([
                'scp',
                '-i', config.get('ec2', 'key_path'),
                '-o', 'StrictHostKeyChecking=no',
                'scripts/setup', 'scripts/matches',
                '%s@%s:'%(config.get('ec2', 'user_name'),instance.ip_address)])

        print('Running remote scripts.')

        for instance in self.reser.instances:
            subprocess.check_call([
                'ssh',
                '-f',
                '-i', '%s' % config.get('ec2', 'key_path'),
                '-o', 'StrictHostKeyChecking=no',
                '%s@%s'%(config.get('ec2', 'user_name'),instance.ip_address),
                subprocess.list2cmdline([
                    'screen',
                    '-d',
                    '-m',
                    './setup',
                    config.get('aws', 'access_key_id'),
                    config.get('aws', 'secret_access_key'),
                    config.get('aws', 'region'),
                    self.queue_url,
                    config.get('commoncrawl', 'base'),
                    config.get('scraper', 'regex'),
                    config.get('scraper', 'thread_count'),
                    config.get('s3', 'results_bucket')])])

    def track_progress(this):
        conn = boto.sqs.connect_to_region(
            config.get('aws', 'region'),
            aws_access_key_id=config.get('aws', 'access_key_id'),
            aws_secret_access_key=config.get('aws', 'secret_access_key'))

        queue = conn.get_queue(config.get('sqs', 'queue'))

        while True:
            att = queue.get_attributes()
            waiting = att['ApproximateNumberOfMessages']
            progress = att['ApproximateNumberOfMessagesNotVisible']

            sys.stdout.write('\r%s waiting, %s in progress.' % (
                waiting,
                progress))
            sys.stdout.flush()

            if waiting == '0' and progress == '0':
                break

            sleep(5)

        sys.stdout.write('\n')
        print('Finished! Results should be uploading to your S3 bucket.')
        print('This can take a minute. Note: new AWS services still running.')
        print('It is up to you to delete them or continue to be charged.')

def main():
    fill_config()
    job = Job()
    job.confirm_s3()
    job.setup_sqs()
    job.setup_ec2_workers()
    job.wait_until_running()
    job.run_scripts()

    print('Pouch now fully running on AWS! Will begin tracking progress.')
    print('You may exit this program at any time without interupting Pouch.')

    job.track_progress()

if __name__ == '__main__':
    main()
