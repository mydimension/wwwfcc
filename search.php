<?php
require ( dirname ( __FILE__ ) . '/includes/base.php' );
$smarty = new Smarty_Fcc;

$smarty->debugging = false;
$smarty->force_compile = false;

// this is the default page title
$smarty->assign ( 'page_title', 'amfm.cc Radio Search' );

if ( stristr ( $_SERVER['HTTP_ACCEPT'], 'text/vnd.wap.wml' ) ) {
	$index_tpl   = 'index.wml.tpl';
	$listing_tpl = 'listing.wml.tpl';
} else {
	$index_tpl   = 'index.tpl';
	$listing_tpl = 'listing.tpl';
}

// form not submitted so this is a normal request
if ( ! isset ( $_REQUEST['search'] ) ) {
	$smarty->display ( $index_tpl );
	exit;
}

$search  = $_REQUEST['search'];
$map     = new GoogleMapAPI();
$geocode = $map->getGeocode( $search );      //caching
//$geocode = $map->geoGetCoords( $search );  //non-caching

if ( ! isset( $geocode['lat'] ) && ! isset( $geocode['lon'] ) ) {
	$smarty->display( $index_tpl );
	exit;
}

// make sure a vaild band was selected
if ( ! isset ( $valid_bands[$_REQUEST['band']] ) ) {
	$smarty->display ( $index_tpl );
	exit;
}

$radio_band = $_REQUEST['band'];

$sql_band['FM'] = "
SELECT fme.facility_id,
       fac.fac_callsign,
       fac.fac_frequency,
       fac.comm_city,
       fac.comm_state,
       fac.fac_type,
       ROUND( @ant_lat := ( IF( fme.lat_dir = 'N', 1, -1 ) *
              ( fme.lat_deg + ( fme.lat_min / 60 ) +
              ( fme.lat_sec / 3600 ) ) ), 6
            ) AS ant_lat,
       ROUND( @ant_lon := ( IF( fme.lon_dir = 'E', 1, -1 ) *
              ( fme.lon_deg + ( fme.lon_min / 60 ) +
              ( fme.lon_sec / 3600 ) ) ), 6
            ) AS ant_lon,
       ROUND( @distance := DEGREES( ACOS(
              SIN( RADIANS( @ant_lat     ) ) *
              SIN( RADIANS( ".$geocode['lat']." ) ) +
              COS( RADIANS( @ant_lat     ) ) *
              COS( RADIANS( ".$geocode['lat']." ) ) *
              COS( RADIANS( @ant_lon - ".$geocode['lon']." ) ) ) ) * 69.09, 1
            ) AS distance,
       CONCAT( IF( @ant_lat > ".$geocode['lat'].", 'N', 'S' ),
               IF( @ant_lon > ".$geocode['lon'].", 'E', 'W' )
             ) AS ant_direction,
       fme.horiz_erp,
       ROUND( (     fme.horiz_erp * 1000     ) /
              ( 4 * PI() * POW( @distance, 2 ) ), 2
            ) AS intensity
FROM application app,
     facility    fac,
     fm_eng_data fme
WHERE app.facility_id       = fac.facility_id
  AND app.application_id    = fme.application_id
  AND fme.eng_record_type   = 'C'
  AND fme.fm_dom_status     = 'LIC'
  AND app.app_service    LIKE 'FM'
  AND fac.fac_type         IN ( 'ED', 'H', 'L' )
  AND fac.fac_callsign REGEXP '^W|K.*'
HAVING intensity >= 1
ORDER BY fac_frequency ASC;";

$sql_band['AM'] = "
SELECT ame.facility_id,
       fac.fac_callsign,
       fac.fac_frequency,
       fac.comm_city,
       fac.comm_state,
       ams.hours_operation,
       ame.station_class,
       ROUND( @ant_lat := ( IF( ams.lat_dir = 'N', 1, -1 ) *
              ( ams.lat_deg + ( ams.lat_min / 60 ) +
              ( ams.lat_sec / 3600 ) ) ), 6
            ) AS ant_lat,
       ROUND( @ant_lon := ( IF( ams.lon_dir = 'E', 1, -1 ) *
              ( ams.lon_deg + ( ams.lon_min / 60 ) +
              ( ams.lon_sec / 3600 ) ) ), 6
            ) AS ant_lon,
       ROUND( @distance := DEGREES( ACOS(
              SIN( RADIANS( @ant_lat     ) ) *
              SIN( RADIANS( ".$geocode['lat']." ) ) +
              COS( RADIANS( @ant_lat     ) ) *
              COS( RADIANS( ".$geocode['lat']." ) ) *
              COS( RADIANS( @ant_lon - ".$geocode['lon']." ) ) ) ) * 69.09, 1
            ) AS distance,
       CONCAT( IF( @ant_lat > ".$geocode['lat'].",  'N', 'S' ),
               IF( @ant_lon > ".$geocode['lon'].", 'E', 'W' )
             ) AS ant_direction,
       ams.power,
       ROUND( IF( ams.hours_operation IN ( 'U', 'D' ), 1.2, 1 )*
              ( (       ams.power * 1000       ) /
              (   4 * PI() * POW( @distance, 2 ) ) ), 2
            ) AS intensity
FROM application app,
     facility    fac,
     am_ant_sys  ams,
     am_eng_data ame
WHERE app.facility_id       = fac.facility_id
  AND app.application_id    = ame.application_id
  AND app.application_id    = ams.application_id
  AND ame.am_dom_status     = 'L'
  AND ams.eng_record_type   = 'C'
  AND app.app_service    LIKE 'AM'
  AND fac.fac_callsign REGEXP '^W|K.*'
HAVING intensity >= 1
ORDER BY fac_frequency ASC;";

// get search results
$rs =& $db->CacheExecute ( $sql_band[$radio_band] )
	or die ( $db->ErrorMsg() );
//echo $sql_band[$radio_band];

// variable assignment
$smarty->assign ( 'page_title', $radio_band . ' Results for ' . $search );
$smarty->assign ( 'band'      , $radio_band     );
$smarty->assign ( 'tbl_array' , $rs->GetArray() );
$smarty->assign ( 'query'     , $search         );

$smarty->display ( $listing_tpl, $radio_band.'|'.$search );
?>
