import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { HttpClientModule } from '@angular/common/http';
import { AppComponent } from './app.component';
import { DataCollectionComponent } from './data-collection/data-collection.component';

@NgModule({
  declarations: [
    AppComponent,
    DataCollectionComponent
  ],
  imports: [
    BrowserModule,
    HttpClientModule  // Make sure this line is present
  ],
  providers: [],
  bootstrap: [AppComponent]
})
export class AppModule { }