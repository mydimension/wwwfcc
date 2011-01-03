<?php
$HOMEDIR = $_SERVER['DOCUMENT_ROOT'];

dl ( '../lib/adodb.so' ) or die;

require ( $HOMEDIR.'../phplib/smarty/Smarty.class.php' );
require ( $HOMEDIR.'../phplib/adodb/adodb.inc.php' );
require ( $HOMEDIR.'../phplib/GoogleMapAPI-2.3/GoogleMapAPI.class.php' );

// preferred cache time in seconds. 604800 = 7 days
define ( CACHE_TIME, 604800 );

$valid_bands = array ( 'AM' => 'AM', 'FM' => 'FM' );

class Smarty_Fcc extends Smarty {
	function Smarty_Fcc() {
		global $valid_bands;

		$this->Smarty();

		$this->template_dir = $HOMEDIR.'../etc/templates/';
		$this->compile_dir  = $HOMEDIR.'../tmp/templates_c/';
		$this->config_dir   = $HOMEDIR.'../etc/configs/';
		$this->cache_dir    = $HOMEDIR.'../tmp/cache/';
		$this->caching      = false;

		$this->load_filter ( 'output', 'gzip' );

		$this->assign ( 'radio_bands', $valid_bands );
	}
}

include('includes/dbconn.php');

// set ADOdb to use associative arrays
$ADODB_FETCH_MODE = ADODB_FETCH_ASSOC;

// set ADOdb cache directory
$ADODB_CACHE_DIR = $HOMEDIR.'../tmp/adodb_cache';

// set cache time for ADOdb
$db->cacheSecs = CACHE_TIME;

// enable SQL logging
$db->LogSQL ( TRUE );

/* custom functions */

// be sure apache is configured for the .wml extensions!
function insert_header ( $params ) {
	// this function expects $content argument
	if ( empty ( $params [ 'content' ] ) ) return;
	header ( $params [ 'content' ] );
	return;
}
?>
