#!/usr/local/bin/perl

# ftp://ftp.fcc.gov/pub/Bureaus/MB/Databases/cdbs/all-cdbs-files.zip

# prefix `perl Makefile.PL` with
#   PREFIX=~/lib LIB=~/lib
#BEGIN { unshift @INC, '/home/mydimension/lib/' };

use strict;
use DBI;
use POSIX;
use Getopt::Long;
use POSIX qw(:signal_h :sys_wait_h);

use constant WGET     => '/usr/bin/wget';
use constant GUNZIP   => '/bin/gunzip';
use constant DBREPO   => 'ftp://ftp.fcc.gov/pub/Bureaus/MB/Databases/cdbs';
use constant MAX_KIDS => 2;

sub _Log;

$SIG{CHLD} = \&Reaper;

my %kids = ();
my $ParentPid = $$;
my $sigset   = new POSIX::SigSet;
my $blockset = new POSIX::SigSet ( SIGCHLD );
sub _Block   { sigprocmask ( SIG_BLOCK  , $blockset, $sigset ) }
sub _Unblock { sigprocmask ( SIG_SETMASK, $sigset            ) }

my %opts = (debug => 1);
GetOptions ( \%opts,
	'quiet|q',
	'debug|d',
);

# disable ouput buffering
$| = 1;


my $dbh = DBI->connect (
	'', # DSN string
	'', # username
	'', # password
	#{ PrintError => 0 }
	{ PrintError => 1, RaiseError => 1 }
) or die "Couldn't connect to database: $DBI::errstr\n";


my %inserts = (
	am_ant_sys => $dbh->prepare (
		'INSERT INTO `am_ant_sys` (
			`ant_mode`,
			`ant_sys_id`,
			`application_id`,
			`aug_count`,
			`bad_data_switch`,
			`domestic_pattern`,
			`dummy_data_switch`,
			`efficiency_restricted`,
			`efficiency_theoretical`,
			`feed_circ_other`,
			`feed_circ_type`,
			`hours_operation`,
			`lat_deg`,
			`lat_dir`,
			`lat_min`,
			`lat_sec`,
			`lon_deg`,
			`lon_dir`,
			`lon_min`,
			`lon_sec`,
			`q_factor`,
			`q_factor_custom_ind`,
			`power`,
			`rms_augmented`,
			`rms_standard`,
			`rms_theoretical`,
			`tower_count`,
			`eng_record_type`,
			`biased_lat`,
			`biased_long`,
			`mainkey`,
			`am_dom_status`,
			`lat_whole_specs`,
			`lon_whole_specs`,
			`ant_dir_ind`,
			`grandfathered_ind`,
			`specified_hrs_range`,
			`augmented_ind`,
			`last_change_date`
		)
		VALUES (' . join ( ',', ('?') x 39 ) . ')' ),
	am_eng_data => $dbh->prepare (
		'INSERT INTO `am_eng_data` (
			`ant_monitor`,
			`application_id`,
			`broadcast_schedule`,
			`encl_fence_dist`,
			`facility_id`,
			`sampl_sys_ind`,
			`station_class`,
			`time_zone`,
			`region_2_class`,
			`am_dom_status`,
			`old_station_class`,
			`specified_hours`,
			`feed_circ_other`,
			`feed_circ_type`,
			`last_change_date`
		)
		VALUES (' . join ( ',', ('?') x 15 ) . ')' ),
	application => $dbh->prepare (
		'INSERT INTO `application` (
			`app_arn`,
			`app_service`,
			`application_id`,
			`facility_id`,
			`file_prefix`,
			`comm_city`,
			`comm_state`,
			`fac_frequency`,
			`station_channel`,
			`fac_callsign`,
			`general_app_service`,
			`app_type`,
			`paper_filed_ind`,
			`dtv_type`,
			`frn`,
			`shortform_app_arn`,
			`shortform_file_prefix`,
			`corresp_ind`,
			`assoc_facility_id`,
			`network_affil`,
			`sat_tv_ind`,
			`comm_county`,
			`comm_zip1`,
			`comm_zip2`,
			`last_change_date`
		)
		VALUES (' . join ( ',', ('?') x 25 ) . ')' ),
	facility => $dbh->prepare (
		'INSERT INTO `facility` (
			`comm_city`,
			`comm_state`,
			`eeo_rpt_ind`,
			`fac_address1`,
			`fac_address2`,
			`fac_callsign`,
			`fac_channel`,
			`fac_city`,
			`fac_country`,
			`fac_frequency`,
			`fac_service`,
			`fac_state`,
			`fac_status_date`,
			`fac_type`,
			`facility_id`,
			`lic_expiration_date`,
			`fac_status`,
			`fac_zip1`,
			`fac_zip2`,
			`station_type`,
			`assoc_facility_id`,
			`callsign_eff_date`,
			`tsid_ntsc`,
			`tsid_dtv`,
			`digital_status`,
			`sat_tv`,
			`network_affil`,
			`nielsen_dma`,
			`last_change_date`
		)
		VALUES (' . join ( ',', ('?') x 29 ) . ')' ),
	fm_eng_data => $dbh->prepare (
		'INSERT INTO `fm_eng_data` (
			`ant_input_pwr`,
			`ant_max_pwr_gain`,
			`ant_polarization`,
			`ant_rotation`,
			`antenna_id`,
			`antenna_type`,
			`application_id`,
			`asd_service`,
			`asrn_na_ind`,
			`asrn`,
			`avg_horiz_pwr_gain`,
			`biased_lat`,
			`biased_long`,
			`border_code`,
			`border_dist`,
			`docket_num`,
			`effective_erp`,
			`elev_amsl`,
			`elev_bldg_ag`,
			`eng_record_type`,
			`facility_id`,
			`fm_dom_status`,
			`gain_area`,
			`haat_horiz_rc_mtr`,
			`haat_vert_rc_mtr`,
			`hag_horiz_rc_mtr`,
			`hag_overall_mtr`,
			`hag_vert_rc_mtr`,
			`horiz_bt_erp`,
			`horiz_erp`,
			`lat_deg`,
			`lat_dir`,
			`lat_min`,
			`lat_sec`,
			`lon_deg`,
			`lon_dir`,
			`lon_min`,
			`lon_sec`,
			`loss_area`,
			`max_ant_pwr_gain`,
			`max_haat`,
			`max_horiz_erp`,
			`max_vert_erp`,
			`multiplexor_loss`,
			`power_output_vis_kw`,
			`predict_coverage_area`,
			`predict_pop`,
			`rcamsl_horiz_mtr`,
			`rcamsl_vert_mtr`,
			`station_class`,
			`terrain_data_src`,
			`vert_bt_erp`,
			`vert_erp`,
			`num_sections`,
			`present_area`,
			`percent_change`,
			`spacing`,
			`terrain_data_src_other`,
			`trans_power_output`,
			`mainkey`,
			`lat_whole_secs`,
			`lon_whole_secs`,
			`station_channel`,
			`lic_ant_make`,
			`lic_ant_model_num`,
			`min_horiz_erp`,
			`haat_horiz_calc_ind`,
			`erp_w`,
			`trans_power_output_w`,
			`market_group_num`,
			`last_change_date`
		)
		VALUES (' . join (',', ('?') x 71 ) . ')' ),
);

my %mon = (
	Jan => 1,
	Feb => 2,
	Mar => 3,
	Apr => 4,
	May => 5,
	Jun => 6,
	Jul => 7,
	Aug => 8,
	Sep => 9,
	Oct => 10,
	Nov => 11,
	Dec => 12
);

# be nice to the system
POSIX::nice ( 5 );

foreach my $tbl_name ( keys %inserts ) {
	for ( my $sec = 0;
	         scalar ( keys %kids ) >= MAX_KIDS;
	         $sec++ )
	{
		$sec % 10 or _Log sprintf "Sleeping for child slots to free up...";
		sleep 1;
	}
		
	_Log "Downloading $tbl_name data file";

	# get content of data file from FCC repository
	my $get_prg = join ' ',
		WGET, '-qO', '-', "@{[DBREPO]}/$tbl_name.zip",
		'|', GUNZIP, '-c', '-';

	my @infile = `$get_prg`;
	next unless @infile;

	_Block;

	my $kidpid = $opts{debug} ? 0 : fork;
	if ( $kidpid ) {
		#
		# Parent process
		#
		_Log "** Adding pid '$kidpid' to kid table";
		$kids{$kidpid}++;
		_Unblock;
	} else {
		#
		# Child process
		#
		_Unblock;

		_Log "$tbl_name - begin: " . localtime();

		# empty the table
		$dbh->do ( "TRUNCATE TABLE $tbl_name" ) or
			_Log "Could not empty table: $tbl_name - $DBI::errstr";

		foreach ( @infile ) {
			# remove the trailing | at the end of each line
			chomp;
			s/\|\r?\n?$//;

			my @args = ();

			foreach ( split ( /\|/, $_, -1 ) ) {
				# take care of NULL values - ignore values which eval to 0
				$_ eq '' and push ( @args, undef ), next;

				# ex: Mar 12 2001 1:42PM
				if ( /(\w{3}) (\d{1,2}) (\d{4}) (\d{1,2}):(\d{2})(\w{2})/ ) {
					my $hr  = $4;
					   $hr += 12 if $6  eq 'PM';
					   $hr  = 0  if $hr ==  24;
					push @args, sprintf ( '%4d-%02d-%02d %02d:%02d:%02d',
        	                               $3, $mon{$1}, $2, $hr, $5, 0 );
					next;
				}

				# ex: 03/12/2001
				/(\d{2})\/(\d{2})\/(\d{4})/ and
					push ( @args, "$3-$1-$2 00:00:00" ),
					next;

				# everything else
				push @args, $_;
			}

			# insert the entry into the database
			$inserts{$tbl_name}->execute ( @args )
				or _Log "Failed to execute query: $DBI::errstr\n";
		}

		_Log (
			"$tbl_name - end: " . localtime(),
			"Records: " . scalar ( @infile )
		);

		_Log "Cleaning $tbl_name";
		$dbh->do ("ANALYZE TABLE $tbl_name;");
		$dbh->do ("OPTIMIZE TABLE $tbl_name;");

		exit ( 0 ) unless $opts{debug};
	}
}

_Unblock;

for ( my $sec = 0;
         %kids;
         $sec++ )
{
	$sec % 10 or _Log sprintf "Waiting for %d kid%s [@{[ keys %kids ]}]",
		scalar(keys %kids), scalar(keys %kids) != 1 ? 's' : '';
	sleep 1;
}

$dbh->disconnect;

exit 0;

sub progress_bar {
	my ( $got, $total, $width, $char ) = @_;
	$width ||= 40;
	$char  ||= '=';
	my $num_width = length $total;
	sprintf ( "%3s%% [%-${width}s] %${num_width}s of %s records\r",
		int 100 * $got / +$total,
		$char x ( ( $width - 1 ) * $got / $total ) . '>',
		$got, $total );
}

#
# The SIGCHLD handler to catch exiting child processes
#
sub Reaper {    # SIGCHLD handler
	return if $opts{debug};

	while ( my $kidpid = waitpid ( -1, WNOHANG ) ) {
		last unless $kidpid > 0;

		unless ( $kids{$kidpid} ) {
			_Log "Didn't recognize pid $kidpid as one of our kids";
			next;
        }

        my $exit_value = $? >> 8;
        _Log "Reaped child process $kidpid, status was $exit_value";

        delete $kids{$kidpid};
    } continue {
        _Unblock;
    }
    $SIG{CHLD} = \&Reaper; # save us from SysV style signaling
}

sub _Log {
	$opts{quiet} and return;

	my $prefix = $$ == $ParentPid ? ' **PARENT**' : " [$$] ";
	print STDERR localtime() . $prefix, join ( "\n\t", @_ ) . "\n";
}
