<?php
require ( dirname ( __FILE__ ) . '/includes/base.php' );
$smarty = new Smarty_Fcc;

$smarty->debugging = false;

$smarty->assign ( 'page_title', 'amfm.cc Radio Search' );

if ( stristr ( $_SERVER['HTTP_ACCEPT'], 'text/vnd.wap.wml' ) ) {
	$smarty->display ( 'index.wml.tpl' );
} else {
	$smarty->display ( 'index.tpl' );
}
?>
