import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { DataCollectionComponent } from './data-collection/data-collection.component';
import { FeatureCardComponent } from './feature-card/feature-card.component';

const routes: Routes = [
  { path: '', redirectTo: '/data-collection', pathMatch: 'full' },
  { path: 'data-collection', component: DataCollectionComponent },
  { path: 'feature-card', component: FeatureCardComponent },
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})

export class AppRoutingModule { }
